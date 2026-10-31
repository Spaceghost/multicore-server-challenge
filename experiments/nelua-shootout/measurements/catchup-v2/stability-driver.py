#!/usr/bin/env python3
"""Guarded selected-app stability command; no comparator or official-score claim.

Run this file with Python 3 from any directory in the research checkout. It uses
the existing shootout.py server/loadgen/monitor primitives, starts local PG in
the same network namespace, and always stops its server/PG and drops its own DB.
An ordinary application UID is mandatory: no root fallback or namespace changes.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

APP_COMMIT = 'bc35c96ef444521151f6f3a78591f39b59f21b6e'
COMPILER_COMMIT = '4b5dfd4a76ce4f6e3c59983295f32f7db68466b4'
WORKSPACE = Path('/workspace/scratch/7de47ba8b27a')
spec = importlib.util.spec_from_file_location('shootout', Path(__file__).resolve().parents[2] / 'shootout.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError as error:
        return 'unavailable: ' + type(error).__name__


def git(app, *arguments):
    return harness.command(['git', '-C', str(app), *arguments], timeout=30).stdout.strip()


def application_identity(output):
    status = read('/proc/self/status')
    fields = ('Uid:', 'Gid:', 'CapInh:', 'CapPrm:', 'CapEff:', 'CapBnd:', 'CapAmb:', 'NoNewPrivs:', 'Seccomp:')
    selected = '\n'.join(line for line in status.splitlines() if line.startswith(fields))
    evidence = {'uid': os.getuid(), 'euid': os.geteuid(), 'gid': os.getgid(),
                'uid_map': read('/proc/self/uid_map'), 'gid_map': read('/proc/self/gid_map'),
                'status': selected, 'attempts': []}
    (output / 'uid-map.txt').write_text(evidence['uid_map'] + '\n')
    (output / 'gid-map.txt').write_text(evidence['gid_map'] + '\n')
    (output / 'capabilities.txt').write_text(selected + '\n')
    if os.geteuid() != 0:
        evidence['ordinary_uid_available'] = True
        prefix = []
    else:
        evidence['ordinary_uid_available'] = False
        prefix = None
        candidates = [
            ['setpriv', '--reuid=65534', '--regid=65534', '--clear-groups'],
            ['runuser', '-u', 'nobody', '--'],
        ]
        for candidate in candidates:
            if not shutil.which(candidate[0]):
                evidence['attempts'].append({'command': candidate, 'error': 'not installed'})
                continue
            result = harness.command(candidate + ['id', '-u'], check=False, timeout=10)
            evidence['attempts'].append({'command': candidate + ['id', '-u'],
                'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
            if result.returncode == 0 and result.stdout.strip() not in ('', '0'):
                evidence['ordinary_uid_available'] = True
                prefix = candidate
                break
    (output / 'identity-preflight.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return prefix, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-checkout', type=Path, default=WORKSPACE / 'multicore-server-challenge')
    parser.add_argument('--output', type=Path, default=WORKSPACE / 'catchup-v2-stability')
    parser.add_argument('--pg-bin', type=Path, default=WORKSPACE / 'pg18/bin')
    parser.add_argument('--pg-data', type=Path, default=WORKSPACE / 'pg18-data')
    parser.add_argument('--pg-port', type=int, default=55432)
    parser.add_argument('--pg-user', default=os.environ.get('PGUSER', 'root'))
    parser.add_argument('--loadgen', type=Path, default=WORKSPACE / 'challenge-tools/loadgen')
    parser.add_argument('--port', type=int, default=3110)
    parser.add_argument('--users', type=int, default=8000)
    parser.add_argument('--warmup', type=int, default=10)
    parser.add_argument('--ramp', type=int, default=5)
    parser.add_argument('--measure', type=int, default=300)
    parser.add_argument('--tail', type=int, default=3)
    parser.add_argument('--think-scale', type=float, default=0.1)
    parser.add_argument('--template', default='conduit_seed')
    parser.add_argument('--articles', type=int, default=500000)
    parser.add_argument('--seed', type=int, default=2309)
    args = parser.parse_args()
    args.secret = 'multicore-server-challenge'
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error('output must be empty; existing measurements are never overwritten')
    app = args.app_checkout.resolve()
    submission = app / 'submissions/nelua-epoll-spaceghost'
    binary = submission / 'bin/conduit'
    head = git(app, 'rev-parse', 'HEAD')
    pin = re.search(r'^NELUA_REV=([0-9a-f]+)$', (submission / 'build.sh').read_text(), re.M).group(1)
    dirty = git(app, 'status', '--porcelain', '--', 'submissions/nelua-epoll-spaceghost')
    metadata = {'created_utc': datetime.now(timezone.utc).isoformat(), 'source_commit': head,
        'compiler_commit': pin, 'source_dirty': bool(dirty),
        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
        'users': args.users, 'warmup_s': args.warmup, 'ramp_s': args.ramp,
        'measure_s': args.measure, 'tail_s': args.tail, 'think_scale': args.think_scale,
        'template': args.template, 'articles': args.articles, 'official_score': False,
        'load_generator_location': 'same host',
        'proc_pid_namespace_matches': harness.proc_pid_namespace_matches(),
        'application_rss': 'unavailable' if not harness.proc_pid_namespace_matches() else 'sampled',
        'pg_root_guard': 'existing local diagnostic build only; no patch applied by this driver'}
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    if head != APP_COMMIT or pin != COMPILER_COMMIT or dirty:
        raise RuntimeError('selected clean app/compiler source does not match this driver')
    prefix, identity = application_identity(output)
    if prefix is None:
        result = {'status': 'blocked', 'reason': 'no representable ordinary application UID',
            'postgres_started': False, 'application_started': False, 'measurement_started': False,
            'eligible': False, 'official_score': False}
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result), flush=True)
        return 2
    # The wrapper proves its actual UID/capabilities immediately before exec.
    wrapper = output / 'application-identity.py'
    wrapper.write_text("""import json, os, pathlib, sys
status=pathlib.Path('/proc/self/status').read_text()
caps={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in status.splitlines() if line.startswith('Cap')}
identity={'application_uid':os.getuid(),'application_euid':os.geteuid(),'capabilities':caps}
print('APPLICATION_IDENTITY '+json.dumps(identity),flush=True)
if os.geteuid()==0 or any(int(value,16) for name,value in caps.items() if name!='CapBnd'): sys.exit(79)
os.execv(sys.argv[1],[sys.argv[1]])
""")
    launcher = output / 'start-ordinary.sh'
    launcher.write_text('#!/bin/sh\nexec ' + shlex.join(prefix + [sys.executable, str(wrapper), str(binary)]) + '\n')
    os.environ.update(PGHOST='127.0.0.1', PGPORT=str(args.pg_port), PGUSER=args.pg_user,
                      PSQL=str(args.pg_bin / 'psql'))
    pg = None
    pglog = None
    database = f'nc_stability_{os.getpid()}_{int(time.time())}'
    created = False
    try:
        if (args.pg_data / 'postmaster.pid').exists():
            raise RuntimeError('PG data already has a postmaster; refusing overlapping ownership')
        pglog = (output / 'postgres.log').open('w')
        pg = subprocess.Popen([str(args.pg_bin / 'postgres'), '-D', str(args.pg_data),
            '-h', '127.0.0.1', '-p', str(args.pg_port), '-k', ''], stdout=pglog,
            stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(150):
            if pg.poll() is not None:
                raise RuntimeError('local PG exited before readiness; see postgres.log')
            try:
                if harness.psql('SELECT 1') == '1':
                    break
            except (OSError, RuntimeError, subprocess.SubprocessError):
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError('local PG did not become ready')
        metadata['pg_settings'] = harness.psql("SELECT name||'='||setting FROM pg_settings WHERE name IN "
            "('max_connections','shared_buffers','synchronous_commit','fsync','full_page_writes') ORDER BY name")
        if int(harness.psql('SELECT count(*) FROM articles', args.template)) != args.articles:
            raise RuntimeError('template is not the expected full article seed')
        (output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        harness.create_database(database, args.template)
        created = True
        case = {'launcher': str(launcher), 'cwd': str(submission)}
        with harness.Server(case, database, args.port, output, args.secret) as server:
            with harness.Monitor(server, output) as monitor:
                print('warmup started', flush=True)
                harness.load_run(args, server, args.users, output, 'warmup', warmup=True)
                print('300-second measurement started', flush=True)
                merged = harness.load_run(args, server, args.users, output, 'measured')
                harness.health_request(args.port)
                if server.process.poll() is not None:
                    raise RuntimeError('server exited during the hold')
            peak = max((sample['connections'] for sample in monitor.samples), default=-1)
            rss = [sample['rss_mb'] for sample in monitor.samples if sample['rss_mb'] is not None]
            result = {'status': 'completed', 'eligible': bool(merged['verdict']['pass'])
                and not merged['verdict']['lg_limited'] and 0 < peak <= 95,
                'verdict': merged['verdict'], 'overall': merged['overall'],
                'boxes': merged['boxes'], 'db_connections_peak': peak,
                'application_rss_peak_mb': max(rss) if rss else None,
                'server_alive_after_hold': True, 'official_score': False}
            (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
            print(json.dumps(result), flush=True)
        return 0
    finally:
        cleanup = {}
        if created:
            try:
                harness.drop_database(database)
                cleanup['owned_database_dropped'] = True
            except Exception as error:
                cleanup['database_cleanup_error'] = type(error).__name__
        if pg is not None and pg.poll() is None:
            pg.send_signal(signal.SIGINT)
            pg.wait(timeout=30)
            cleanup['owned_postgres_stopped'] = True
        if pglog:
            pglog.close()
        (output / 'cleanup.json').write_text(json.dumps(cleanup, indent=2) + '\n')


if __name__ == '__main__':
    sys.exit(main())
