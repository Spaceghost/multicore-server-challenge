# Local Nelua comparison — 2026-11-16

This investigation uses the challenge workload and the ten entries listed in the
[video description](https://www.youtube.com/watch?v=TIyvOtGjnzc). These are local,
fixed-concurrency diagnostics, not a reproduction of the official capacity score.
Measurements were completed locally before preparing a separate review branch.

## Revisions

- Original submission: PR #146 at `bc35c96ef444521151f6f3a78591f39b59f21b6e`.
- Official compiler: `edubart/nelua-lang` at
  `a58450563e2d2ec49bff499865c8b5cfdf6ff81a`, replacing the Spaceghost fork at
  `4b5dfd4a76ce4f6e3c59983295f32f7db68466b4`.
- Comparison sources: upstream snapshot
  `6145e7291a3625c184a58b63b86ed9d1f7304700`. The source manifest records each
  submission tree and all 293 original files' SHA-256 hashes.

Compiling the original application with either compiler produces byte-identical
C, SHA-256 `3a7c1cdc5c81396f9994de3b5ad3b08d0e410cbdd45ca5ad9c6e670b61efd603`.
The compiler migration itself therefore explains no application speedup. The new
build explicitly regenerates C and links companion sources without relying on a
cached companion executable.

## Paired end-to-end latency

The final default passes both runs at each tested load: 1,000, 5,000 and 20,000
users. All six final-default runs have zero request errors, no loadgen limitation,
and a peak of 20 database connections.

The following comparison uses **the same final binary**, changing only
`READ_GATHER_ADAPTIVE=0` versus `1`. Values are medians of two runs per mode/load.

| Users | Fixed 8 ms p95 | Adaptive p95 | Adaptive p99 | p95 reduction |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 12.85 ms | 4.95 ms | 8.32 ms | 61.4% |
| 5,000 | 15.26 ms | 6.53 ms | 12.29 ms | 57.2% |

Median response latency also falls from 8.92 to 2.82 ms at 1,000 users, and from
9.29 to 3.14 ms at 5,000. Request rates remain about 265 and 1,318 req/s respectively;
the normal think time dominates the offered rate at these loads.

With spare read workers, the collector uses a 2 ms window. When all other read
workers are executing batches, it keeps the original 8 ms window. Execution counts
are protected by the queue mutex, and collection never holds its lock during a DB
call. A single read worker retains the original window.

## Headroom at 20,000 users

Two 40-second measurements per entry, with reversed order. The p95 range is shown
because the shared host produces substantial high-load variation.

| Entry | Median req/s | Median p95 [range], ms | Median p99, ms | Request errors | SLO passes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original Nelua PR #146 | 5,198.1 | 297.1 [282.4–311.8] | 399.7 | 0 | 2/2 |
| Final Nelua, adaptive (default) | 5,257.5 | 162.8 [61.6–263.9] | 269.3 | 0 | 2/2 |
| Final Nelua, fixed-8 control | 5,152.1 | 518.5 [175.7–861.2] | 790.9 | 1,566 | 1/2 |
| Rust #201, video #1 | 5,195.7 | 185.4 [181.2–189.6] | 360.2 | 0 | 2/2 |
| Nish #225, video #2 | 5,179.4 | 248.8 [245.1–252.5] | 441.7 | 0 | 2/2 |

No headroom run is flagged as loadgen-limited. The fixed-8 control has 1,566 HTTP
503 responses in its first run and fails that run’s latency limits. The adaptive
default passes both runs with zero errors. The original also passes both runs.
Rates include all measured requests, including errors in the failed control.

These measurements support lower latency at the tested loads. They do not find
the maximum sustainable concurrency or establish an official leaderboard rank.

## Video-entry comparison at fixed loads

This first matrix uses the original PR and an optimized **fixed-8-ms** snapshot,
before adaptive collection was added. The final adaptive binary has its separate
paired comparison above. Table order follows the video, not measured capacity.

| Entry | 1,000 users p95, ms | 5,000 users p95, ms | 5,000 users req/s | Completed trials |
| --- | ---: | ---: | ---: | ---: |
| Original Nelua #146 | 12.04 | 13.45 | 1,317.7 | 4/4 |
| Optimized Nelua, fixed 8 ms | 11.78 | 15.93 | 1,317.5 | 4/4 |
| Optimized fixed 8 ms, sharing off | 11.77 | 13.66 | 1,317.5 | 4/4 |
| 1. Rust #201 — theCatWisel | 78.78 | 83.04 | 1,305.3 | 4/4 |
| 2. Nish #225 — amritk | 91.30 | 90.40 | 1,300.3 | 4/4 |
| 3. Rust #212 — WorriedArrow | 80.09 | 82.85 | 1,304.8 | 4/4 |
| 4. Zig #168 — nick-potts * | 94.62 | 95.04 | 1,302.8 | 4/4 |
| 5. C #203 — unorig-username | 166.72 | 173.76 | 1,288.8 | 4/4 |
| 6. Swift io_uring #207 — Tabonx * | 87.55 | 102.97 | 1,318.0 | 2/4 |
| 7. Swift epoll #224 — akbashev | 20.65 | 23.71 | 1,315.4 | 4/4 |
| 8. ASM #130 — nickita-khylkouski | 3.17 | 5.00 | 1,318.9 | 4/4 |
| 9. F# #210 — delneg | 9.52 | 11.09 | 1,318.2 | 4/4 |
| 10. Java #185 — stohirov | 49.05 | 89.60 | 1,305.5 | 4/4 |

All 50 completed workload runs have zero request errors and pass the workload SLO;
none is loadgen-limited. Two additional trials fail during smaller-ring Swift
startup, one at each load. Its table values therefore each represent **one run**.
The stock versions of the two starred entries cannot start on Bak; the table uses
the explicitly modified ring-size variants described below.

Sharing alone does not establish a mixed-workload throughput gain: switching
`READ_COALESCE` off gives effectively the same fixed-load throughput, and latency
does not improve consistently when it is enabled. Its deterministic access/parameter
reductions are reported separately. The paired test isolates the end-to-end gain
from adaptive collection.

## Targeted improvements

Measured on Bak, with baseline/candidate/candidate/baseline order for JSON and
six measured SQL executions per version after warmups:

| Operation | Original | Candidate | Change |
| --- | ---: | ---: | ---: |
| JSON emitter, ordinary 4 KiB text | 1,469 MiB/s | 4,951 MiB/s | 3.37× throughput |
| JSON emitter, UTF-8 4 KiB text | 1,458 MiB/s | 4,921 MiB/s | 3.37× throughput |
| JSON emitter, sparse escapes | 1,135 MiB/s | 1,615 MiB/s | 1.42× throughput |
| Global page SQL, offset 100,000,000 | 48.49 ms | 0.547 ms | 88.7× faster SQL execution |
| Text-value accesses, 32 distinct viewers | 3,680 | 755 | 79.5% fewer accesses |
| Bound parameter bytes, 106-request fixture | 1,142 | 584 | 48.9% fewer bytes |

JSON rates use process CPU time for 250,000 calls per sample and the same emitted
bytes. They measure the emitter, not HTTP throughput. Text-value counts instrument
libpq accessors during rendering; they do not measure PostgreSQL wire traffic.
The SQL numbers are `EXPLAIN ANALYZE` execution times, not HTTP latency.

The word scanner retains scalar escaping for control bytes, quotes and backslashes.
Read sharing authenticates every request independently and retains data only in
its frozen batch. Public article fragments exclude both personalized booleans;
every response still owns its own output buffer.

The offset guard uses the span between minimum and maximum article IDs as a safe
upper bound on page cardinality. Out-of-range pages skip the index walk while
still querying the fresh capped count. Numeric arithmetic handles signed-bigint
extremes. It also preserves valid pages beyond the 1,000-count reporting cap.

## Method

Bak is an Intel i5-10400 shared host. An isolated Ubuntu 24.04 Incus container has
six logical CPUs, a 5 GiB memory limit, 200,000 file descriptors and a 64 MiB locked
memory limit. Exact affinity and process status samples are retained. Source,
builds and PostgreSQL use separate task volumes on the existing
`sharkdeck-build-nvme` ZFS pool. No host sysctls or database-wide tuning changed.
[Incus documents](https://linuxcontainers.org/incus/docs/main/reference/instance_options/#kernel-resource-limits)
`limits.kernel.memlock` as a per-process resource limit.

PostgreSQL 18.7 uses the canonical schema and complete deterministic seed: 100,000
users, 500,000 articles, 200 tags, 1,989,808 follows, 1,250,377 article-tag links,
4,990,637 favorites and 2,494,001 comments. Every reference row-count/content
fingerprint matches. Loading canonical pre-data, then the original TSVs, then
canonical post-data preserves the logical schema; physical index packing differs
from the incremental reference loader. Every case receives this same layout.

Every run creates a fresh database using PostgreSQL `STRATEGY FILE_COPY`, reads its
files sequentially, starts a fresh server, and uses the unmodified challenge
loadgen. The client and database share the container with the server. Runs use
1,000 and 5,000 virtual users, normal think scale `1`, 10 seconds of ramp, 20 seconds
of measurement and 15 seconds of tail. The same deterministic run ID is used for
each case at a given round/load. Two rounds use shuffled and reversed case order.
These short windows and the shared host limit capacity conclusions.

The initial matrix uses the original PR and the frozen optimized fixed-8 snapshot
with `READ_COALESCE=0` and `1`. The paired adaptive stage uses the final binary
with `READ_GATHER_ADAPTIVE=0` and `1`, at the same two loads and durations.
The headroom stage uses 20,000 users, 40-second measurement windows, and the
original, both final gathering modes, Rust #201 and Nish #225.
`READ_BATCH_STATS=1` is set for every Nelua configuration. Other server settings use their launchers'
defaults. Database connection peaks, loadgen limitation flags, errors, percentile
latencies and executable hashes are retained with the raw outputs.

### Two hardware adaptations

The stock Zig #168 and Swift io_uring #207 entries build but return `ENOMEM` when
allocating their large rings on Bak. Small-ring probes succeed. Increasing locked
memory alone did not fix this. Both stock entries passed conformance on Alienware.
Their original Bak sources and binaries are retained, with startup failures
reported rather than assigned a performance score.

Separate variants change only these ring sizes:

| Entry | Stock SQ / CQ | Diagnostic SQ / CQ | Compiler |
| --- | ---: | ---: | --- |
| Zig #168 | 4,096 / 65,536 | 4,096 / 8,192 | Zig 0.17.0 |
| Swift io_uring #207 | 8,192 / 65,536 | 4,096 / 8,192 | Swift 6.4.1 |

Both variants pass all 197 conformance steps. The smaller-ring Swift variant
still has the two startup allocation failures reported above. The original sources remain
unchanged; `small-rings.patch` records the two changed lines. Results for these
variants must not be treated as stock-PR scores.

## Validation

The candidate passes the full-seed 197-step suite on Bak. All runnable comparison
configurations pass the same 197-step suite on the official development fixture.
The additional SQL fixture passes 117 assertions against independent SQL oracles,
including gaps, negative IDs, bigint extremes, counts and deep offsets. ASan/UBSan
checks cover every byte value, unaligned string tails, exact allocation boundaries,
response ownership and per-viewer flags. The native-runtime audit passes. Sixteen transport scenarios cover two/four
workers, both gathering modes, concurrent execution, correct active counts, the
busy-worker collection window and shutdown, under ASan/UBSan.

## Evidence and reproduction

The tested sources were prepared on `local/official-nelua-20261116` in
`/home/jack/Projects/multicore-server-challenge`. The review snapshot uses
`review/official-nelua-optimizations-20261117`, separately from the PR #146 branch.

Alienware evidence is retained at
`/home/jack/workspaces/multicore-nelua-2026-11-16`. Its accelerated-think-time HDD
runs are overload diagnostics and are excluded from the Bak comparison.

Bak evidence is in Incus container `multicore-official-nelua-20261116`, under
`/srv/ai/artifacts/multicore/official-nelua-20261116` (`/evidence`). It includes the
source/binary manifests, all build logs, conformance results, component benchmark
plans, raw loadgen files, process samples and the exact driver. The first attempt
with an 8 MiB locked-memory limit is preserved separately as
`memlock8MiB-attempt` and excluded from the final comparison.

The raw results and analysis are also mirrored locally under
`/home/jack/workspaces/multicore-nelua-2026-11-16/bak`, with a complete result
archive at `bak-results.tar.gz` beside that directory. Source/binary hash manifests
identify the frozen and final builds.

The initial matrix driver command is:

```sh
python3 /evidence/benchmark.py \
  --cases /evidence/cases-with-compat.json --output /evidence/comparison \
  --template conduit_seed --articles 500000 --users 1000,5000 \
  --rounds 2 --measure 20 --think-scale 1
```

Choose a new output directory for a repeat. The retained driver assumes the
prepared source paths, PostgreSQL credentials and unchanged seed template.

The final paired and headroom commands are:

```sh
python3 /evidence/benchmark.py \
  --cases /evidence/cases-adaptive.json --output /evidence/adaptive-comparison \
  --template conduit_seed --articles 500000 --users 1000,5000 \
  --rounds 2 --measure 20 --think-scale 1
python3 /evidence/benchmark.py \
  --cases /evidence/cases-headroom-final.json --output /evidence/headroom \
  --template conduit_seed --articles 500000 --users 20000 \
  --rounds 2 --measure 40 --think-scale 1
```

Across the three stages there are 70 attempts: 68 completed workload runs (one
control run fails latency limits) and two startup allocation failures.
All results, including failures, are retained.
