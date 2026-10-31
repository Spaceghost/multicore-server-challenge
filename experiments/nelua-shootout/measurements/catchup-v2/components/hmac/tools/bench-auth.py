#!/usr/bin/env python3
"""Small paired benchmark of real request parsing, verification, and cleanup.

--baseline-source is the unchanged request.c; the candidate is this checkout's
request.c. This is a CPU microbenchmark, not a leaderboard workload or score.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import shlex
import statistics
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=')


def corpus():
    entries = []
    now = int(time.time())
    for i in range(48):
        header = {'alg': 'HS256', 'typ': 'JWT'} if i % 2 else {'typ': 'JWT', 'alg': 'HS256'}
        claims = {'sub': str(i + 1), 'iat': now, 'exp': now + 3600}
        if i % 3 == 0:
            claims['nbf'] = now - 60
        if i % 4 == 0:
            claims['description'] = 'snow 雪 and a quote " ' * (i % 13 + 1)
        expected = i + 1
        if i >= 40:
            claims['exp'] = now - 1
            expected = -1
        message = b64(json.dumps(header, separators=(',', ':')).encode()) + b'.' + b64(
            json.dumps(claims, ensure_ascii=False, separators=(',', ':')).encode())
        key = b'wrong' if 32 <= i < 40 else b'actual-request-benchmark-secret'
        if 32 <= i < 40:
            expected = -1
        token = message + b'.' + b64(hmac.digest(key, message, hashlib.sha256))
        entries.append(f'{expected}\t{token.decode()}\n')
    entries.extend(['0\t-\n'] * 8)
    return ''.join(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-source', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=30000)
    parser.add_argument('--repeats', type=int, default=2, help='ABBA pairs')
    args = parser.parse_args()
    compiler = shlex.split(os.environ.get('CC', 'cc'))
    flags = ['-std=gnu11', '-O3', '-flto', '-fno-semantic-interposition', '-march=native',
             '-Wall', '-Wextra', '-Werror', '-I' + str(ROOT / 'src')]
    observations = {'baseline': [], 'candidate': []}
    with tempfile.TemporaryDirectory(prefix='nc-auth-bench-') as directory:
        temporary = Path(directory)
        tokens = temporary / 'corpus.tsv'
        tokens.write_text(corpus())
        for name, source in [('baseline', args.baseline_source), ('candidate', ROOT / 'src/request.c')]:
            subprocess.run(compiler + flags + [str(source), str(ROOT / 'src/bcrypt.c'),
                str(ROOT / 'tests/request_auth_bench.c'), '-pthread', '-lcrypto', '-lcrypt',
                '-o', str(temporary / name)], check=True)
        environment = {**os.environ, 'JWT_SECRET': 'actual-request-benchmark-secret'}
        for _ in range(args.repeats):
            for name in ('baseline', 'candidate', 'candidate', 'baseline'):
                observation = json.loads(subprocess.check_output(
                    [str(temporary / name), str(tokens), str(args.iterations)],
                    env=environment, text=True, timeout=30))
                observations[name].append(observation)
        for name, values in observations.items():
            print(name, json.dumps({'median_cpu_ns': statistics.median(v['cpu_ns'] for v in values),
                                   'samples': values}))
        baseline = statistics.median(v['cpu_ns'] for v in observations['baseline'])
        candidate = statistics.median(v['cpu_ns'] for v in observations['candidate'])
        print(f'candidate CPU change: {(candidate / baseline - 1) * 100:.2f}%')


if __name__ == '__main__':
    main()
