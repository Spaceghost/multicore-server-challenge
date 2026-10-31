# Paired full-seed top-five shootout for bc35c96

[Workflow run 41158333666](https://github.com/Spaceghost/multicore-server-challenge/actions/runs/41158333666) tested research head `c025e83ae6f11835fbd5f8f98eceedfd3d602cd5`. Its Nelua submission tree, `22bd396b8a7ab29df68eac2d8682c2b59c16aef1`, exactly matches [PR #146](https://github.com/arjaythedev/multicore-server-challenge/pull/146) head `bc35c96ef444521151f6f3a78591f39b59f21b6e`. Only Nelua and the frozen published top five are compared.

All six original install/build scripts exited 0/0. The scale-1.0 seed contains 500,000 articles and passed the reference fingerprints; all six official conformance logs explicitly show **197 steps, 197 passed, 0 failed**. Every requested measurement finished: **24/24 measured, 17/24 eligible**. All 24 passed the application SLO verdict with **zero application errors**. Maximum sampled application database connections: **20**. The seven ineligible rows are retained and flagged for whole-host CPU exceeding 75%; there are no missing comparator measurements.

At the eligible 1000-user point, Nelua has lower median p95 and p99 than RustCat, Zig, WorriedArrow and C#. ASM remains faster. At 5000 users Nelua has higher latency than all five and both repetitions are CPU-flagged. **No overall capacity winner or official score is established.**

Each case used a fresh verified full-seed clone, two rounds, 10-second warm-up, 5-second ramp, 20-second measurement, 3-second tail and think scale **0.1**. The same deterministic RNG ID is shared across all six cases per round/load/phase: `shoot-s2309-r{round}-u{users}-{warmup|measured}`. All 48 raw phase files confirm eight such groups; warm-up and measurement IDs differ. These are paired random inputs, not identical timings or completed request traces. Two rounds are a partial balanced-order block. Accelerated user counts are not equivalent to official unscaled users.

## 1000-user medians

All 12 repetitions at this load are eligible.

| Entry | Req/s | p50 ms | p95 ms | p99 ms | Host CPU % | App RSS MiB | CPU flags / 2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nelua-epoll-spaceghost | 2581.000 | 9.363 | 14.779 | 17.863 | 30.775 | 13.557 | 0 |
| rust-epoll-theCatWisel | 2549.275 | 15.843 | 19.967 | 21.567 | 18.774 | 6.566 | 0 |
| zig-iouring-nick-potts | 2328.250 | 52.559 | 91.071 | 96.415 | 17.570 | 124.205 | 0 |
| rust-epoll-WorriedArrow | 2567.075 | 11.063 | 18.799 | 21.535 | 19.959 | 51.873 | 0 |
| asm-epoll-nickita-khylkouski | 2635.150 | 0.573 | 1.984 | 3.016 | 45.333 | 8.148 | 0 |
| csharp-epoll-aot-gichamba | 2541.100 | 17.487 | 25.199 | 27.047 | 20.377 | 31.217 | 0 |

## 5000-user medians

These medians include every measured repetition, including the flagged rows. The last column preserves load-generator eligibility; they are diagnostic values, not a capacity ranking.

| Entry | Req/s | p50 ms | p95 ms | p99 ms | Host CPU % | App RSS MiB | CPU flags / 2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nelua-epoll-spaceghost | 8700.450 | 200.063 | 267.327 | 310.527 | 99.392 | 24.824 | 2 |
| rust-epoll-theCatWisel | 11922.150 | 42.671 | 63.007 | 73.151 | 66.597 | 16.562 | 0 |
| zig-iouring-nick-potts | 11101.675 | 71.583 | 122.047 | 134.655 | 68.663 | 156.039 | 0 |
| rust-epoll-WorriedArrow | 12142.475 | 32.895 | 50.671 | 67.151 | 75.768 | 84.516 | 1 |
| asm-epoll-nickita-khylkouski | 12820.075 | 9.999 | 25.783 | 38.975 | 93.276 | 12.648 | 2 |
| csharp-epoll-aot-gichamba | 12044.650 | 39.871 | 67.999 | 91.679 | 84.908 | 70.873 | 2 |

The high-load flags are Nelua (both rounds, 99% host CPU), C# (both, 86%/84%), ASM (both, 94%/93%) and WorriedArrow (round 1, 77%). WorriedArrow round 2 is unflagged at 74.6403%; RustCat and Zig are unflagged in both rounds. Flags use the official load generator's whole-box CPU test. PostgreSQL, applications and the client share this runner, so that test does not isolate client-only CPU. All flagged runs still pass application SLOs; the largest p95/p99 anywhere in the matrix is 272.895/320.511 ms.

The runner has 4 CPUs/~16 GiB (AMD EPYC 7763), PostgreSQL 18.6 with recorded stock settings, and a descriptor hard limit of 65,536. Runtime effective capabilities are zero and io_uring is available. It differs from the dedicated 8-vCPU/16GB official server, external clients, 200,000 descriptors and prescribed PostgreSQL configuration. Neither these user counts nor delivered throughput may be extrapolated into an official ceiling. Earlier unpaired CI runs are separate evidence and are not pooled into these medians.

All five comparator commit/tree/toolchain records match `pins.tsv`, all recorded sources are clean, and each entry retains the same executable path/hash across conformance and its four measurements. The current persistent HTTP/1.1 readiness probe matches the official client behavior; no comparator source was patched.

An independent read-only artifact audit reproduced the six explicit conformance counts, 24 unique slots, all source pins, 48 paired RNG IDs, statuses/errors, seven flags, all summary medians and sampled resource aggregates. Process CPU/RSS samples are valid and nonzero here; process CPU spans ramp/measurement/tail, while load-generator host CPU uses its measurement window. RSS sums process mappings and may double-count shared pages. Database peaks are one-second observations, not proof against shorter spikes.

All 287 original artifact members are preserved here byte for byte as UTF-8 tabular/log/official-load-generator JSON files. `ARTIFACT.tsv` records the original downloadable ZIP identity; `SHA256SUMS.tsv` covers this text archive and README. The original ZIP remains linked from the workflow run. The workflow exits 2 because the full requested matrix is not entirely eligible, despite complete measurements and passing application SLOs.
