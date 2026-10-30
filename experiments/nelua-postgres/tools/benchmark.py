#!/usr/bin/env python3
"""Compare prepared pgbench calls against equivalent ordinary SQL JSON output.

DATABASE_URL names an existing database with the fixed Conduit schema and
nelua_conduit installed. This benchmark never creates or changes database rows.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys


EXPERIMENT = Path(__file__).resolve().parents[1]
CASES = {
    "native": EXPERIMENT / "bench" / "native.sql",
    "sql-json": EXPERIMENT / "bench" / "sql-json.sql",
}


def command(args, **kwargs):
    proc = subprocess.run(args, text=True, encoding="utf-8", capture_output=True, **kwargs)
    if proc.returncode:
        # Never print the command: its final argument contains DATABASE_URL.
        raise RuntimeError(f"{Path(args[0]).name} failed ({proc.returncode}):\n{proc.stdout}{proc.stderr}")
    return proc.stdout, proc.stderr


def psql(args, database_url, *, file=None, sql=None):
    cmd = [args.psql, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"]
    if file:
        cmd += ["-f", str(file)]
    elif sql:
        cmd += ["-c", sql]
    cmd += ["-d", database_url]
    return command(cmd, env={**os.environ, "PGCLIENTENCODING": "UTF8"})[0].strip()


def measure(args, database_url, case, seconds, round_number):
    print(f"{round_number}: {case}, {seconds}s, clients={args.clients}, threads={args.threads}",flush=True)
    cmd = [args.pgbench, "-n", "-M", "prepared", "-c", str(args.clients),
           "-j", str(args.threads), "-T", str(seconds), "-f", str(CASES[case]), database_url]
    stdout,stderr = command(cmd, timeout=seconds+30)
    raw = (stdout + stderr).strip()
    tps = re.search(r"^tps\s*=\s*([0-9]+(?:\.[0-9]+)?)",raw,re.MULTILINE)
    latency = re.search(r"^latency average\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*ms",raw,re.MULTILINE)
    failed = re.search(r"^number of failed transactions:\s*([0-9]+)",raw,re.MULTILINE)
    if not tps or not latency:
        raise RuntimeError("Cannot parse pgbench TPS/latency:\n"+raw)
    if (failed and int(failed.group(1)) != 0) or "ERROR:" in raw:
        raise RuntimeError("pgbench reported failed transactions:\n"+raw)
    return {"case":case,"round":round_number,"tps":float(tps.group(1)),
            "latency_ms":float(latency.group(1)),"raw":raw}


def client_hardware():
    lines=[f"- Client platform: `{platform.platform()}`",
           f"- Client architecture: `{platform.machine()}`; visible logical CPUs: {os.cpu_count()}"]
    cpu=Path("/proc/cpuinfo")
    if cpu.exists():
        match=re.search(r"^model name\s*:\s*(.+)$",cpu.read_text(),re.MULTILINE)
        if match:
            lines.append(f"- Client CPU: {match.group(1)}")
    mem=Path("/proc/meminfo")
    if mem.exists():
        match=re.search(r"^MemTotal:\s*(\d+)\s*kB",mem.read_text(),re.MULTILINE)
        if match:
            lines.append(f"- Client visible memory: {int(match.group(1))/1024**2:.2f} GiB (container limits may be lower)")
    return lines


def report(args, records, metadata):
    medians={case:{key:statistics.median(r[key] for r in records if r["case"]==case)
                   for key in ("tps","latency_ms")} for case in CASES}
    parts=["# Nelua/PostgreSQL page microbenchmark", "",
           f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} (UTC).", "",
           "This measures one anonymous, ten-article global page with a capped count over the existing dataset. "
           "It compares a prepared call to `nc_articles(0,10,0)` with a prepared, page-first ordinary SQL query "
           "using `json_build_object` and `json_agg`. Both return text JSON; decoded outputs were checked equal "
           "before timing. Neither benchmark caches response data or changes rows.", "",
           "## Scope and environment", "",
           "This is a shared development run, without CPU isolation or process pinning. "
           "Client host information is shown below; the database host may differ. "
           "These results do not measure HTTP, JWT verification, bcrypt, write traffic, the complete challenge workload, "
           "or an official full-seed run. They support no leaderboard ranking or application-speed extrapolation.", "",
           *client_hardware(),
           f"- PostgreSQL server: `{metadata['server']}`",
           f"- Client tools: `{metadata['psql']}`; `{metadata['pgbench']}`",
           f"- Dataset row counts: `{json.dumps(metadata['rows'],sort_keys=True)}`",
           f"- Settings: prepared protocol; {args.clients} clients; {args.threads} threads; "
           f"{args.seconds} seconds per measured run; {args.rounds} rounds per case.",
           "- Warm-up: one unmeasured one-second run per case; measured order alternates each round.", "",
           "## Results", "",
           "| Case | Median TPS | Median average latency (ms) |",
           "| --- | ---: | ---: |"]
    for case in CASES:
        parts.append(f"| {case} | {medians[case]['tps']:.2f} | {medians[case]['latency_ms']:.3f} |")
    ratio=medians["native"]["tps"]/medians["sql-json"]["tps"]
    parts += ["",f"Observed native/SQL median TPS ratio: **{ratio:.3f}×** for this query and run only.","",
              "| Round | Case | TPS | Average latency (ms) |","| ---: | --- | ---: | ---: |"]
    for record in records:
        parts.append(f"| {record['round']} | {record['case']} | {record['tps']:.2f} | {record['latency_ms']:.3f} |")
    parts += ["","## Raw pgbench output",""]
    for record in records:
        parts += [f"### Round {record['round']}: {record['case']}","","```text",record["raw"],"```",""]
    return "\n".join(parts),medians


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds",type=int,default=3,help="seconds per measured run (default: 3; set explicitly for longer runs)")
    parser.add_argument("--clients",type=int,default=1)
    parser.add_argument("--threads",type=int,default=1)
    parser.add_argument("--rounds",type=int,default=3)
    parser.add_argument("--output",type=Path,default=EXPERIMENT/"results"/"benchmark.md")
    parser.add_argument("--psql",default=os.environ.get("PSQL","psql"))
    parser.add_argument("--pgbench",default=os.environ.get("PGBENCH","pgbench"))
    args=parser.parse_args()
    if min(args.seconds,args.clients,args.threads,args.rounds) < 1:
        parser.error("seconds, clients, threads, and rounds must all be positive")
    if args.threads > args.clients:
        parser.error("threads cannot exceed clients")
    database_url=os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL must name an existing database with nelua_conduit installed")

    outputs={case:json.loads(psql(args,database_url,file=file)) for case,file in CASES.items()}
    if outputs["native"] != outputs["sql-json"]:
        raise RuntimeError("Native and SQL JSON outputs differ; benchmark refused")
    print("Output parity: PASS",flush=True)
    metadata={
        "server":psql(args,database_url,sql="SELECT version();"),
        "psql":command([args.psql,"--version"])[0].strip(),
        "pgbench":command([args.pgbench,"--version"])[0].strip(),
        "rows":json.loads(psql(args,database_url,sql="""SELECT json_build_object(
          'users',(SELECT count(*) FROM public.users),'articles',(SELECT count(*) FROM public.articles),
          'tags',(SELECT count(*) FROM public.tags),'favorites',(SELECT count(*) FROM public.favorites),
          'comments',(SELECT count(*) FROM public.comments),'follows',(SELECT count(*) FROM public.follows));""")),
    }
    for case in CASES:
        measure(args,database_url,case,1,"warm-up (excluded)")
    records=[]
    for round_number in range(1,args.rounds+1):
        order=list(CASES)
        if round_number % 2 == 0:
            order.reverse()
        for case in order:
            records.append(measure(args,database_url,case,args.seconds,round_number))
    markdown,medians=report(args,records,metadata)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(markdown,encoding="utf-8")
    for case,value in medians.items():
        print(f"{case}: median {value['tps']:.2f} TPS; average latency {value['latency_ms']:.3f} ms",flush=True)
    print(f"Report: {args.output.resolve()}",flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError,subprocess.SubprocessError,json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}",file=sys.stderr)
        sys.exit(1)
