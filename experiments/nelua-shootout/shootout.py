#!/usr/bin/env python3
"""Same-host, top-five-only diagnostic shootout. Never an official ceiling score.

The PostgreSQL server is supplied by the caller through normal PG* variables.
This script never starts/reconfigures PostgreSQL or changes kernel settings.
It creates and drops only its own nc_shoot_* databases. All server executions
run as the invoking user; only the contest's per-child descriptor limit is set.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import resource
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUR_NAME = "nelua-epoll-spaceghost"
TOP5 = ("rust-epoll-theCatWisel", "zig-iouring-nick-potts",
        "rust-epoll-WorriedArrow", "asm-epoll-nickita-khylkouski",
        "csharp-epoll-aot-gichamba")
ALL_NAMES = (OUR_NAME,) + TOP5
FIELDS = ("round", "position", "users", "name", "variant", "status", "rps", "p50_ms",
          "p95_ms", "p99_ms", "error_rate", "errors", "host_cpu_pct",
          "loadgen_cpu_pct", "app_cpu_core_eq", "app_rss_peak_mb", "app_db_connections_peak",
          "lg_limited", "reason", "directory")
IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
NATIVE_KNOBS = {"READ_GATHER_SERIAL", "READ_PIPELINE", "DB_READ_THREADS",
                "DB_WRITE_THREADS", "DB_AUTH_THREADS"}


def write_tsv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = ("key", "value")
        rows = [{"key": k, "value": str(v).replace("\n", " | ")} for k, v in rows.items()]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def command(argv, *, env=None, cwd=None, timeout=120, log=None, check=True):
    # Do not print argv: database connection arguments can contain credentials.
    result = subprocess.run(argv, env=env, cwd=cwd, text=True, encoding="utf-8",
                            errors="replace", capture_output=True, timeout=timeout)
    if log:
        Path(log).write_text(result.stdout + result.stderr)
    if check and result.returncode:
        raise RuntimeError(f"{Path(argv[0]).name} exited {result.returncode}; see captured log")
    return result


def psql(sql, database="postgres", *, timeout=120):
    return command([os.environ.get("PSQL", "psql"), "-X", "-q", "-A", "-t",
                    "-v", "ON_ERROR_STOP=1", "-d", database, "-c", sql],
                   timeout=timeout).stdout.strip()


def identifier(value):
    if not IDENTIFIER.fullmatch(value):
        raise ValueError("database names must be simple lowercase PostgreSQL identifiers")
    return value


def create_database(name, template):
    psql(f"CREATE DATABASE {identifier(name)} TEMPLATE {identifier(template)} STRATEGY FILE_COPY", timeout=300)


def drop_database(name):
    psql(f"DROP DATABASE IF EXISTS {identifier(name)} WITH (FORCE)", timeout=120)


def io_uring_probe():
    if platform.machine() not in ("x86_64", "aarch64") or platform.system() != "Linux":
        return "unsupported probe architecture"
    libc = ctypes.CDLL(None, use_errno=True)
    parameters = ctypes.create_string_buffer(256)
    fd = libc.syscall(ctypes.c_long(425), ctypes.c_uint(1), ctypes.byref(parameters))
    if fd >= 0:
        os.close(fd)
        return "available"
    number = ctypes.get_errno()
    return f"blocked: errno={number} {os.strerror(number)}"


def text_file(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return "unavailable"


def git(*args):
    return command(["git", "-C", str(REPO), *args], timeout=30).stdout.strip()


def read_pins():
    with (HERE / "pins.tsv").open() as stream:
        pins = list(csv.DictReader(stream, delimiter="\t"))
    if tuple(row["name"] for row in pins) != TOP5:
        raise ValueError("pins.tsv must contain exactly the frozen five comparators in rank order")
    for rank, row in enumerate(pins, 1):
        if row["rank"] != str(rank):
            raise ValueError("invalid frozen leaderboard ranks")
    return {row["name"]: row for row in pins}


def read_cases(path=None):
    if path:
        with Path(path).open() as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
    else:
        rows = [{"name": name, "launcher": str(REPO / "submissions" / name / "start.sh"),
                 "cwd": str(REPO / "submissions" / name)} for name in ALL_NAMES]
    names = [row.get("name") for row in rows]
    if len(rows) != 6 or set(names) != set(ALL_NAMES):
        raise ValueError("cases must be exactly Nelua plus the frozen top five; no substitutes/duplicates")
    pins = read_pins()
    for row in rows:
        launcher = row.get("launcher") or row.get("binary")
        if not launcher:
            raise ValueError("every case requires a launcher or binary path")
        if row.get("sourcepin") and row["name"] in pins:
            expected = pins[row["name"]]
            if row["sourcepin"] not in (expected["source_commit"], expected["source_tree"]):
                raise ValueError("case sourcepin differs from frozen comparator manifest")
        elif row.get("sourcepin"):
            head = git("rev-parse", "HEAD")
            directory = f"submissions/{OUR_NAME}"
            tree = git("rev-parse", f"{head}:{directory}")
            dirty = subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", head,
                                    "--", directory]).returncode != 0
            if row["sourcepin"] not in (head, tree) or dirty:
                raise ValueError("supplied Nelua sourcepin requires an unchanged current commit/tree")
        row["launcher"] = str(Path(launcher).expanduser().resolve())
        row["cwd"] = str(Path(row.get("cwd") or Path(row["launcher"]).parent).expanduser().resolve())
    return {row["name"]: row for row in rows}


def parse_variants(values):
    if not values:
        return {"default": {}}
    variants = {}
    for value in values:
        name, separator, settings = value.partition(":")
        if not separator or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name) or name in variants:
            raise ValueError("native variants need unique simple names and NAME:KEY=VALUE syntax")
        parsed = {}
        for item in settings.split(",") if settings else ():
            key, separator, setting = item.partition("=")
            if not separator or key not in NATIVE_KNOBS or not setting.isdigit() or key in parsed:
                raise ValueError("variant settings must be documented numeric Nelua process knobs")
            parsed[key] = setting
        variants[name] = parsed
    return variants


def source_metadata(pins):
    records = []
    for name in ALL_NAMES:
        directory = f"submissions/{name}"
        pin = pins.get(name)
        commit = pin["source_commit"] if pin else git("rev-parse", "HEAD")
        tree = git("rev-parse", f"{commit}:{directory}")
        dirty = subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", commit, "--", directory]).returncode != 0
        if pin and (tree != pin["source_tree"] or dirty):
            raise RuntimeError(f"comparator source differs from pinned snapshot: {name}")
        digest = hashlib.sha256()
        # Enumerate tracked source once; never walk huge Cargo/.NET build caches.
        for relative in git("ls-files", "--", directory).splitlines():
            file = REPO / relative
            if file.is_file():
                digest.update(relative.encode() + b"\0" + file.read_bytes())
        records.append({"name": name, "commit": commit, "tree": tree, "dirty": dirty,
                        "tracked_source_sha256": digest.hexdigest(),
                        "toolchain": pin["toolchain"] if pin else "pinned Nelua fork + GCC"})
    return records


def balanced_orders(names, repeats, seed):
    """Williams balanced Latin order; six rounds form a complete position/carryover block."""
    base = list(names)
    random.Random(seed).shuffle(base)
    size = len(base)
    indices = [0]
    low, high = 1, size - 1
    while low <= high:
        indices.append(low)
        low += 1
        if low <= high:
            indices.append(high)
            high -= 1
    return [[base[(value + round_number) % size] for value in indices]
            for round_number in range(repeats)]


def child_limits():
    # Contest systemd sets both limits to 200000. This affects only the child.
    _, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    available = 200000 if hard == resource.RLIM_INFINITY else min(hard, 200000)
    resource.setrlimit(resource.RLIMIT_NOFILE, (available, available))


def health_request(port):
    # Match the official curl/Go HTTP/1.1 readiness clients. urllib forces
    # Connection: close; some asynchronous servers close before their reply
    # when that extra header is present. Drain the response before closing.
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", "/api/tags", headers={"Accept": "application/json"})
        response = connection.getresponse()
        body = response.read()
        return response.status, body[:512]
    finally:
        connection.close()


class Server:
    def __init__(self, case, database, port, directory, secret, settings=None):
        self.case, self.database, self.port, self.directory = case, database, port, directory
        self.secret = secret
        self.settings = settings or {}
        self.process = None
        self.log = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        launcher = Path(self.case["launcher"])
        if not launcher.is_file():
            raise RuntimeError("launcher is not built/present")
        host = os.environ.get("PGHOST", "127.0.0.1")
        if not host or host.startswith("/"):
            host = "127.0.0.1"
        pgport = os.environ.get("PGPORT", "5432")
        authority = f"[{host}]" if ":" in host else host
        app_url = f"postgres://conduit:conduit@{authority}:{pgport}/{self.database}"
        # Keep runtime/tool paths, not arbitrary inherited comparator tuning.
        env = {key: value for key, value in os.environ.items()
               if key in {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "LD_LIBRARY_PATH", "TMPDIR"}}
        env.update(DATABASE_URL=app_url, JWT_SECRET=self.secret,
                   HOST="127.0.0.1", PORT=str(self.port))
        env.update(self.settings)
        self.log = (self.directory / "server.log").open("w")
        argv = ["bash", str(launcher)] if launcher.suffix == ".sh" else [str(launcher)]
        deadline = time.monotonic() + 60
        self.url = f"http://127.0.0.1:{self.port}"
        try:
            try:
                connection = socket.create_connection(("127.0.0.1", self.port), timeout=0.5)
            except ConnectionRefusedError:
                pass
            except OSError as error:
                raise RuntimeError("could not establish that the benchmark port is unused") from error
            else:
                connection.close()
                raise RuntimeError("benchmark port is already listening; refusing an overlapping server")
            self.process = subprocess.Popen(argv, cwd=self.case["cwd"], env=env,
                                            stdout=self.log, stderr=subprocess.STDOUT,
                                            start_new_session=True, preexec_fn=child_limits)
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(f"server exited before health check ({self.process.returncode})")
                try:
                    status, body = health_request(self.port)
                    if status == 200:
                        observed = Path(f"/proc/{self.process.pid}/exe")
                        try:
                            executable = observed.resolve(strict=True)
                            digest = hashlib.sha256(executable.read_bytes()).hexdigest()
                            write_tsv(self.directory / "executable.tsv",
                                      {"path": str(executable), "sha256": digest})
                        except OSError:
                            pass
                        return self
                    detail = f"status={status} body={body!r}"
                except (OSError, http.client.HTTPException) as error:
                    detail = f"{type(error).__name__}: {error}"
                with (self.directory / "health.log").open("a") as health_log:
                    health_log.write(detail + "\n")
                time.sleep(0.2)
            raise RuntimeError("health check failed after 60 seconds")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.process is not None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()


def proc_pid_namespace_matches():
    try:
        return int(Path("/proc/self/stat").read_text().split(" ", 1)[0]) == os.getpid()
    except (OSError, ValueError):
        return False


def group_usage(pid):
    # Some sandboxes expose host /proc but namespace-local Popen PIDs. Those
    # numbers cannot safely identify our child/group; zero would be misleading.
    if not proc_pid_namespace_matches():
        return None, None
    total, ticks, found = 0, 0, False
    page_kb = os.sysconf("SC_PAGE_SIZE") // 1024
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            content = path.read_text()
            fields = content[content.rfind(")") + 2:].split()
            # Fields after comm begin with state; pgrp index 2, rss index21.
            if int(fields[2]) == pid:
                found = True
                total += int(fields[21]) * page_kb
                ticks += int(fields[11]) + int(fields[12])
        except (OSError, ValueError, IndexError):
            continue
    return (total / 1024, ticks) if found else (None, None)


class Monitor:
    def __init__(self, server, directory):
        self.server, self.directory = server, directory
        self.stop = threading.Event()
        self.samples = []

    def __enter__(self):
        def sample():
            while not self.stop.is_set():
                try:
                    count = int(psql("SELECT count(*) FROM pg_stat_activity "
                                     f"WHERE datname='{self.server.database}' AND usename='conduit'", timeout=5))
                except (RuntimeError, ValueError, subprocess.SubprocessError):
                    count = -1
                rss, ticks = group_usage(self.server.process.pid)
                self.samples.append({"time": time.time(), "rss_mb": rss,
                                     "cpu_jiffies": ticks, "connections": count})
                self.stop.wait(1)
        self.thread = threading.Thread(target=sample, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=7)
        write_tsv(self.directory / "application-samples.tsv", self.samples,
                  ("time", "rss_mb", "cpu_jiffies", "connections"))


def load_run(args, server, users, directory, label, *, warmup=False):
    raw = directory / (label + "-box.json")
    seconds = args.warmup if warmup else args.measure
    ramp = min(args.ramp, 3) if warmup else args.ramp
    argv = [str(args.loadgen), "run", "-target", server.url, "-users", str(users),
            "-ramp", f"{ramp}s", "-measure", f"{seconds}s", "-tail", f"{0 if warmup else args.tail}s",
            "-secret", args.secret, "-articles", str(args.articles),
            "-think-scale", str(args.think_scale),
            "-run-id", f"shoot-{directory.name}-{label}-{time.time_ns()}", "-out", str(raw)]
    command(argv, timeout=ramp + seconds + args.tail + 90, log=directory / (label + ".log"))
    if warmup:
        return None
    merged = directory / "merged.json"
    result = command([str(args.loadgen), "merge", "-o", str(merged), str(raw)],
                     timeout=60, log=directory / "merged.txt", check=False)
    if result.returncode not in (0, 3) or not merged.is_file():
        raise RuntimeError("load generator merge did not produce a valid result")
    return json.loads(merged.read_text())


def result_eligible(row):
    return row.get("status") == "pass" and not row.get("lg_limited")


def app_cpu(samples):
    """Average occupied cores over the sampled ramp/measure/tail span."""
    samples = [sample for sample in samples if sample.get("cpu_jiffies") is not None]
    if len(samples) < 2 or samples[-1]["time"] <= samples[0]["time"]:
        return ""
    elapsed = samples[-1]["time"] - samples[0]["time"]
    ticks = samples[-1]["cpu_jiffies"] - samples[0]["cpu_jiffies"]
    return round(max(0, ticks) / os.sysconf("SC_CLK_TCK") / elapsed, 4)


def complete_matrix(rows, rounds, users, variants=None):
    variants = variants or {"default": {}}
    expected = {(round_number, users_at, name, variant) for round_number in range(1, rounds + 1)
                for users_at in users for name in ALL_NAMES
                for variant in (variants if name == OUR_NAME else ("default",))}
    actual = {(row["round"], row["users"], row["name"], row.get("variant", "default"))
              for row in rows if result_eligible(row)}
    return actual == expected


def report(args, rows, conformance, environment):
    complete = complete_matrix(rows, args.rounds, args.users, args.variants)
    labels = [(name, variant) for name in ALL_NAMES
              for variant in (args.variants if name == OUR_NAME else ("default",))]
    clean_conformance = all(conformance.get(name + ":" + variant) == "pass" for name, variant in labels)
    summary = ["# Top-five Nelua diagnostic shootout", "",
               "This compares only Nelua and the frozen published top five. All values are local/CI diagnostics, "
               "not official user ceilings or a replacement for the maintainer's isolated eight-core five-minute holds.", "",
               f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}.", "",
               f"Complete eligible matrix: **{'yes' if complete and clean_conformance else 'no'}**. "
               f"io_uring setup probe: `{environment['io_uring']}`.", "",
               f"Template `{args.template}`; {args.articles} seeded articles; think scale {args.think_scale}; "
               f"ramp {args.ramp}s; warm-up {args.warmup}s; measured {args.measure}s; tail {args.tail}s; "
               f"{args.rounds} round(s). Six rounds complete a Williams position/carryover-balanced block; "
               "shorter runs are an explicitly partial block.", "",
               "| Case | Users | Conformance | Eligible repetitions | Median req/s | p50 ms | p95 ms | p99 ms | Error rate | Peak RSS MiB |",
               "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for users_at in args.users:
        for name, variant in labels:
            selected = [row for row in rows if row["name"] == name and row["variant"] == variant
                        and row["users"] == users_at and result_eligible(row)]
            if selected:
                values = []
                for key in ("rps", "p50_ms", "p95_ms", "p99_ms", "error_rate", "app_rss_peak_mb"):
                    measured = [float(row[key]) for row in selected if row.get(key) not in (None, "")]
                    values.append(f"{statistics.median(measured):.2f}" if measured else "unavailable")
            else:
                values = ["—"] * 6
            label = name + (f" ({variant})" if name == OUR_NAME else "")
            summary.append(f"| {label} | {users_at} | {conformance.get(name + ':' + variant, 'not run')} | {len(selected)} | " + " | ".join(values) + " |")
    summary += ["", "**No shootout winner is declared.** " +
                ("All six cases completed, but these short same-host measurements remain diagnostic; compare individual "
                 "load levels and repeat distributions in `runs.tsv`."
                 if complete and clean_conformance else
                 "At least one comparator/run is blocked, incomplete, failed, or load-generator limited. "
                 "Missing top-five entries are never replaced with a lower-ranked comparator."), "",
                "`runs.tsv` keeps failures and flagged results instead of hiding them. `environment.tsv`, "
                "`sources.tsv`, per-run logs, raw load-generator JSON, and one-second RSS/connection samples "
                "make the measurement auditable. App connection counts above 95 fail that run. "
                "Connection peaks are sampled observations, not a proof that sub-second peaks cannot occur.", ""]
    if args.think_scale != 1:
        summary += ["Think/session time is accelerated for this diagnostic. Its virtual-user count is not comparable "
                    "with official unscaled users.", ""]
    (args.output / "SUMMARY.md").write_text("\n".join(summary))
    return complete and clean_conformance


def environment_metadata(args):
    values = {"platform": platform.platform(), "machine": platform.machine(),
              "visible_cpus": os.cpu_count(), "meminfo": text_file("/proc/meminfo").splitlines()[0],
              "io_uring": io_uring_probe(), "io_uring_disabled": text_file("/proc/sys/kernel/io_uring_disabled"),
              "cgroup_cpu_max": text_file("/sys/fs/cgroup/cpu.max"),
              "cgroup_memory_max": text_file("/sys/fs/cgroup/memory.max"),
              "cgroup_cpuset": text_file("/sys/fs/cgroup/cpuset.cpus.effective"),
              "network_namespace": os.readlink("/proc/self/ns/net") if Path("/proc/self/ns/net").exists() else "unavailable",
              "nofile_parent": resource.getrlimit(resource.RLIMIT_NOFILE),
              "nofile_child": min(200000, resource.getrlimit(resource.RLIMIT_NOFILE)[1])
              if resource.getrlimit(resource.RLIMIT_NOFILE)[1] != resource.RLIM_INFINITY else 200000,
              "nofile_matches_contest": resource.getrlimit(resource.RLIMIT_NOFILE)[1] == resource.RLIM_INFINITY
              or resource.getrlimit(resource.RLIMIT_NOFILE)[1] >= 200000,
              "template": args.template, "think_scale": args.think_scale,
              "load_generator_location": "same host", "official_score": "no",
              "source_head": git("rev-parse", "HEAD")}
    values["process_monitor_pid_namespace_matches"] = proc_pid_namespace_matches()
    values["cpu_model"] = next((line.partition(":")[2].strip()
                                for line in text_file("/proc/cpuinfo").splitlines()
                                if line.startswith("model name")), "unavailable")
    values["clock_ticks_per_second"] = os.sysconf("SC_CLK_TCK")
    values["process_capabilities"] = " | ".join(line for line in text_file("/proc/self/status").splitlines()
                                              if line.startswith(("Cap", "NoNewPrivs", "Seccomp")))
    try:
        values["pg_version"] = psql("SELECT version()")
        values["pg_settings"] = psql("SELECT name || '=' || setting || coalesce(' [' || unit || ']','') FROM pg_settings "
                                    "WHERE name IN ('max_connections','shared_buffers','effective_cache_size',"
                                    "'work_mem','max_worker_processes','max_parallel_workers','max_parallel_workers_per_gather',"
                                    "'synchronous_commit','fsync','full_page_writes','random_page_cost') ORDER BY name")
        values["template_size_bytes"] = psql(f"SELECT pg_database_size('{identifier(args.template)}')")
    except (RuntimeError, subprocess.SubprocessError) as error:
        values["pg_metadata_error"] = type(error).__name__
    return values


def run(args):
    pins, cases = read_pins(), read_cases(args.cases)
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("output directory must be new/empty so prior runs cannot be mistaken for this shootout")
    env = environment_metadata(args)
    write_tsv(args.output / "environment.tsv", env)
    write_tsv(args.output / "sources.tsv", source_metadata(pins),
              ("name", "commit", "tree", "dirty", "tracked_source_sha256", "toolchain"))
    write_tsv(args.output / "launchers.tsv", list(cases.values()), ("name", "launcher", "cwd", "sourcepin"))
    orders = balanced_orders(ALL_NAMES, args.rounds, args.seed)
    write_tsv(args.output / "order.tsv", [{"round": i + 1, "position": p + 1, "name": name}
              for i, order in enumerate(orders) for p, name in enumerate(order)], ("round", "position", "name"))
    conformance, rows = {}, []
    token = f"{os.getpid()}_{int(time.time())}"
    port = args.port

    variants_for = lambda name: args.variants if name == OUR_NAME else {"default": {}}
    labels = [(name, variant, settings) for name in ALL_NAMES
              for variant, settings in variants_for(name).items()]
    write_tsv(args.output / "native-variants.tsv",
              [{"variant": v, "settings": ",".join(f"{k}={x}" for k, x in s.items())}
               for v, s in args.variants.items()], ("variant", "settings"))
    for name, variant, settings in labels:
        key = name + ":" + variant
        directory = args.output / "conformance" / name / variant
        directory.mkdir(parents=True, exist_ok=True)
        if name == TOP5[1] and env["io_uring"] != "available":
            conformance[key] = "blocked: io_uring unavailable"
            (directory / "blocked.txt").write_text(env["io_uring"] + "\n")
            continue
        db = f"nc_shoot_{token}_conformance"
        try:
            create_database(db, args.template)
            with Server(cases[name], db, port, directory, args.secret, settings) as server:
                result = command([str(args.conformance), "-base", server.url, "-secret", args.secret, "-q"],
                                 timeout=180, log=directory / "conformance.log", check=False)
                conformance[key] = "pass" if result.returncode == 0 else "failed"
        except (RuntimeError, OSError, subprocess.SubprocessError) as error:
            conformance[key] = "blocked/failed: " + type(error).__name__
            (directory / "failure.txt").write_text(str(error) + "\n")
        finally:
            try:
                drop_database(db)
            except (RuntimeError, subprocess.SubprocessError):
                pass
        print(f"conformance {key}: {conformance[key]}", flush=True)
    write_tsv(args.output / "conformance.tsv", conformance)

    for round_number, order in enumerate(orders, 1):
        for users in args.users:
            expanded = [(position, name, variant, settings) for position, name in enumerate(order, 1)
                        for variant, settings in variants_for(name).items()]
            # Reverse the ablation order each round rather than always warming the candidate second.
            if round_number % 2 == 0:
                ours = [entry for entry in expanded if entry[1] == OUR_NAME][::-1]
                at = iter(ours)
                expanded = [next(at) if entry[1] == OUR_NAME else entry for entry in expanded]
            for position, name, variant, settings in expanded:
                key = name + ":" + variant
                directory = args.output / f"round-{round_number}" / f"users-{users}" / name / variant
                directory.mkdir(parents=True, exist_ok=True)
                row = {"round": round_number, "position": position, "users": users, "name": name, "variant": variant,
                       "status": "incomplete", "directory": str(directory.relative_to(args.output)),
                       "lg_limited": False, "reason": ""}
                if conformance[key] != "pass":
                    row.update(status="blocked", reason=conformance[key])
                else:
                    db = f"nc_shoot_{token}_r{round_number}"
                    try:
                        create_database(db, args.template)
                        with Server(cases[name], db, port, directory, args.secret, settings) as server:
                            if args.warmup:
                                load_run(args, server, users, directory, "warmup", warmup=True)
                            with Monitor(server, directory) as monitor:
                                merged = load_run(args, server, users, directory, "measured")
                            if server.process.poll() is not None:
                                raise RuntimeError("server exited during the measured run; no restart is attempted")
                            total, verdict = merged["overall"], merged["verdict"]
                            box = merged["boxes"][0]
                            peak = max((s["connections"] for s in monitor.samples), default=-1)
                            row.update(status="pass" if verdict["pass"] and 0 <= peak <= 95 else "failed",
                                       rps=total["rps"], p50_ms=total["p50_ms"], p95_ms=total["p95_ms"],
                                       p99_ms=total["p99_ms"], errors=total["errors"], error_rate=total["error_rate"],
                                       lg_limited=bool(verdict.get("lg_limited")),
                                       host_cpu_pct=box.get("cpu_avg_measure_pct", ""),
                                       loadgen_cpu_pct=box.get("proc_cpu_avg_measure_pct", ""),
                                       app_cpu_core_eq=app_cpu(monitor.samples),
                                       app_rss_peak_mb=max((s["rss_mb"] for s in monitor.samples
                                                           if s["rss_mb"] is not None), default=""),
                                       app_db_connections_peak=peak,
                                       reason="sampled connection limit exceeded" if peak > 95 else
                                              "connection sampling unavailable" if peak < 0 else
                                              "; ".join(verdict.get("fail_reasons", []) + verdict.get("lg_reasons", [])))
                    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
                        row.update(status="failed", reason=type(error).__name__ + ": " + str(error))
                        (directory / "failure.txt").write_text(str(error) + "\n")
                    finally:
                        try:
                            drop_database(db)
                        except (RuntimeError, subprocess.SubprocessError):
                            pass
                rows.append(row)
                write_tsv(args.output / "runs.tsv", rows, FIELDS)
                report(args, rows, conformance, env)
                print(f"round {round_number}, {users} users, {key}: {row['status']} "
                      f"rps={row.get('rps','—')} lg_limited={row['lg_limited']}", flush=True)
    complete = report(args, rows, conformance, env)
    print(f"Report: {args.output / 'SUMMARY.md'}; complete eligible matrix={complete}", flush=True)
    return 0 if complete else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, help="TSV: name, launcher (or binary), optional cwd/sourcepin; exactly six cases")
    parser.add_argument("--nelua-variant", action="append", default=[],
                        help="NAME:KEY=VALUE,...; only Nelua process knobs, never competitor overrides")
    parser.add_argument("--template", default="conduit_seed")
    parser.add_argument("--articles", type=int, default=500000)
    parser.add_argument("--users", default="1000", help="comma-separated equal-load points")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--seed", type=int, default=2309)
    parser.add_argument("--ramp", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--measure", type=int, default=20)
    parser.add_argument("--tail", type=int, default=3)
    parser.add_argument("--think-scale", type=float, default=1.0)
    parser.add_argument("--port", type=int, default=3110)
    parser.add_argument("--conformance", type=Path, required=True)
    parser.add_argument("--loadgen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--secret", default=os.environ.get("JWT_SECRET", "multicore-server-challenge"))
    args = parser.parse_args()
    try:
        args.users = [int(value) for value in args.users.split(",")]
        if not args.users or min(args.users) < 1 or len(set(args.users)) != len(args.users):
            parser.error("users must be unique positive values")
        if not 1 <= args.rounds <= 12 or not 1 <= args.measure <= 300 or not 0 <= args.warmup <= 180:
            parser.error("rounds must be 1..12; measure 1..300s; warmup 0..180s")
        if not 0 <= args.ramp <= 60 or not 0 <= args.tail <= 30 or args.think_scale <= 0 or not math.isfinite(args.think_scale):
            parser.error("invalid ramp, tail, or think scale")
        if not 1 <= args.port <= 65535 or args.articles < 1:
            parser.error("invalid TCP port or seeded article count")
        identifier(args.template)
        args.variants = parse_variants(args.nelua_variant)
        args.output = args.output.resolve()
        args.conformance, args.loadgen = args.conformance.resolve(), args.loadgen.resolve()
        return run(args)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"shootout failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
