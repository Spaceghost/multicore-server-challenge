# Nelua/PostgreSQL page microbenchmark

Generated 2026-10-30T22:29:19+00:00 (UTC).

This measures one anonymous, ten-article global page with a capped count over the existing dataset. It compares a prepared call to `nc_articles(0,10,0)` with a prepared, page-first ordinary SQL query using `json_build_object` and `json_agg`. Both return text JSON; decoded outputs were checked equal before timing. Neither benchmark caches response data or changes rows.

## Scope and environment

This is a shared development run, without CPU isolation or process pinning. Client host information is shown below; the database host may differ. These results do not measure HTTP, JWT verification, bcrypt, write traffic, the complete challenge workload, or an official full-seed run. They support no leaderboard ranking or application-speed extrapolation.

- Client platform: `Linux-6.18.57-x86_64-with-glibc2.39`
- Client architecture: `x86_64`; visible logical CPUs: 9
- Client CPU: AMD EPYC 9V74 80-Core Processor
- Client visible memory: 9.73 GiB (container limits may be lower)
- PostgreSQL server: `PostgreSQL 18.0 on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04) 13.3.0, 64-bit`
- Client tools: `psql (PostgreSQL) 18.0`; `pgbench (PostgreSQL) 18.0`
- Dataset row counts: `{"articles": 1105, "comments": 137, "favorites": 1108, "follows": 2, "tags": 5, "users": 4}`
- Settings: prepared protocol; 1 clients; 1 threads; 3 seconds per measured run; 3 rounds per case.
- Warm-up: one unmeasured one-second run per case; measured order alternates each round.

## Results

| Case | Median TPS | Median average latency (ms) |
| --- | ---: | ---: |
| native | 1709.38 | 0.585 |
| sql-json | 1448.58 | 0.690 |

Observed native/SQL median TPS ratio: **1.180×** for this query and run only.

| Round | Case | TPS | Average latency (ms) |
| ---: | --- | ---: | ---: |
| 1 | native | 1819.77 | 0.550 |
| 1 | sql-json | 1450.53 | 0.689 |
| 2 | sql-json | 1388.19 | 0.720 |
| 2 | native | 1617.37 | 0.618 |
| 3 | native | 1709.38 | 0.585 |
| 3 | sql-json | 1448.58 | 0.690 |

## Raw pgbench output

### Round 1: native

```text
pgbench (18.0)
transaction type: /workspace/scratch/7de47ba8b27a/multicore-server-challenge/experiments/nelua-postgres/bench/native.sql
scaling factor: 1
query mode: prepared
number of clients: 1
number of threads: 1
maximum number of tries: 1
duration: 3 s
number of transactions actually processed: 5457
number of failed transactions: 0 (0.000%)
latency average = 0.550 ms
initial connection time = 1.373 ms
tps = 1819.772797 (without initial connection time)
```

### Round 1: sql-json

```text
pgbench (18.0)
transaction type: /workspace/scratch/7de47ba8b27a/multicore-server-challenge/experiments/nelua-postgres/bench/sql-json.sql
scaling factor: 1
query mode: prepared
number of clients: 1
number of threads: 1
maximum number of tries: 1
duration: 3 s
number of transactions actually processed: 4350
number of failed transactions: 0 (0.000%)
latency average = 0.689 ms
initial connection time = 1.208 ms
tps = 1450.533313 (without initial connection time)
```

### Round 2: sql-json

```text
pgbench (18.0)
transaction type: /workspace/scratch/7de47ba8b27a/multicore-server-challenge/experiments/nelua-postgres/bench/sql-json.sql
scaling factor: 1
query mode: prepared
number of clients: 1
number of threads: 1
maximum number of tries: 1
duration: 3 s
number of transactions actually processed: 4163
number of failed transactions: 0 (0.000%)
latency average = 0.720 ms
initial connection time = 1.222 ms
tps = 1388.188626 (without initial connection time)
```

### Round 2: native

```text
pgbench (18.0)
transaction type: /workspace/scratch/7de47ba8b27a/multicore-server-challenge/experiments/nelua-postgres/bench/native.sql
scaling factor: 1
query mode: prepared
number of clients: 1
number of threads: 1
maximum number of tries: 1
duration: 3 s
number of transactions actually processed: 4851
number of failed transactions: 0 (0.000%)
latency average = 0.618 ms
initial connection time = 1.430 ms
tps = 1617.367142 (without initial connection time)
```

### Round 3: native

```text
pgbench (18.0)
transaction type: /workspace/scratch/7de47ba8b27a/multicore-server-challenge/experiments/nelua-postgres/bench/native.sql
scaling factor: 1
query mode: prepared
number of clients: 1
number of threads: 1
maximum number of tries: 1
duration: 3 s
number of transactions actually processed: 5126
number of failed transactions: 0 (0.000%)
latency average = 0.585 ms
initial connection time = 1.780 ms
tps = 1709.382328 (without initial connection time)
```

### Round 3: sql-json

```text
pgbench (18.0)
transaction type: /workspace/scratch/7de47ba8b27a/multicore-server-challenge/experiments/nelua-postgres/bench/sql-json.sql
scaling factor: 1
query mode: prepared
number of clients: 1
number of threads: 1
maximum number of tries: 1
duration: 3 s
number of transactions actually processed: 4344
number of failed transactions: 0 (0.000%)
latency average = 0.690 ms
initial connection time = 1.536 ms
tps = 1448.577500 (without initial connection time)
```
