# Local full-seed shootout at 8,000 accelerated users

Only Nelua and the frozen top five were considered. This host cannot execute Zig io_uring or build the C# NativeAOT binary, and ASM saturates the shared benchmark host. **Coverage is incomplete; no winner or official score is claimed.**

Two partial balanced-order rounds used fresh full-seed clones, 10-second warm-up, 5-second ramp, 20-second measurement and 3-second tail. Think scale was 0.1. Both Nelua variants use the same final candidate binary and feed query; baseline disables serialized collection and pipelining, tuned enables both. Each variant and runnable comparator passed 197 conformance steps first.

| Case | Eligible repeats | Median req/s | Median p95 ms | Median host CPU | Note |
| --- | ---: | ---: | ---: | ---: | --- |
| nelua-epoll-spaceghost (baseline) | 2 | 18938.03 | 93.02 | 67.78 |  |
| nelua-epoll-spaceghost (tuned) | 2 | 19514.15 | 61.61 | 65.02 |  |
| rust-epoll-WorriedArrow | 2 | 19353.97 | 51.78 | 40.84 |  |
| csharp-epoll-aot-gichamba | 0 | — | — | — | blocked/failed: RuntimeError |
| rust-epoll-theCatWisel | 2 | 18797.88 | 66.62 | 35.55 |  |
| asm-epoll-nickita-khylkouski | 0 | — | — | — | box 0 CPU 77% > 75% |
| zig-iouring-nick-potts | 0 | — | — | — | blocked: io_uring unavailable |

Both Nelua pairs improved: throughput +5.45% / +0.76%, p95 −40.81% / −18.60%. The two-round medians are 18,938.0→19,514.2 req/s (+3.04%) and 93.023→61.615 ms p95 (−33.76%). Repeats are short and vary; these figures describe this diagnostic, not capacity. Host CPU includes PostgreSQL and the co-located load generator. The Rust leaders use substantially less host CPU at this load, so similar throughput here does not imply equal headroom.

Process CPU/RSS samples of zero in the original raw files are **unavailable measurements**, not zero resource use: this sandbox exposes host PIDs in procfs but namespace-local PIDs through system calls. The harness now detects that mismatch and records blanks. The raw files are preserved without rewriting; ignore those two original columns. Host/loadgen CPU, latency, errors, and PostgreSQL connection observations remain usable.

The child descriptor hard limit is 16,384 rather than the official 200,000. PostgreSQL 18 uses the recorded local stock configuration and full verified seed. The scratch PostgreSQL root-start guard was disabled because this sandbox cannot change user; executor/MVCC/query code is unchanged. No such patch is included in the submission or CI.

The captured source metadata predates the final squash and correctly records the candidate as dirty relative to 784535. The published identical candidate is commit `2a07dab2445432f908297a782876d1c851cab137`, submission tree in repository tree `6d076d0564a6ecd4e3d985a9ed833398c7e48c86`; executable hashes are preserved per run. Raw failed cases and load-generator limitation flags remain in `runs.tsv`.

The recorded timing runs used different run IDs, hence independently sampled random trajectories. They are order-paired samples of the same workload distribution, not identical request traces. The newer harness uses a shared deterministic RNG ID per round/load/phase for future measurements.
