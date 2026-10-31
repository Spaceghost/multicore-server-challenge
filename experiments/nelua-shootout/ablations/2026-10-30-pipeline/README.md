# Batch-local read pipeline ablation

Full `conduit_seed` (500,000 articles), PostgreSQL 18, fresh clone per run, same local load generator. Serial collection stays enabled in both modes. One candidate binary includes the optional pipeline; four runs use pipeline 0/1/1/0, 5,000 accelerated virtual users, think scale 0.1, 5-second ramp, 20-second measurement, 3-second tail. Pools remain 4/8/8.

| Mode | Median req/s | Median p95 ms | Median host CPU |
| --- | ---: | ---: | ---: |
| Synchronous read groups |12,176.6 |47.279 |45.57% |
| Pipelined read groups |12,276.5 |41.823 |42.80% |

Median p95 fell 11.5%, throughput rose 0.82%, and host CPU fell 2.77 percentage points. Both order pairs improved; every run has zero errors and is not load-generator limited. These are short development ablations, not official capacity scores. Machine/database limitations match the adjacent gather ablation. Complete loadgen aggregates and batch statistics are retained.

The driver separately passed 20 literal-SELECT checks normally and under ASan/UBSan, including failed PREPARE, aborted commands, 256 KiB responses, result ownership, statement timeouts, and a real backend disconnect followed by reconnect/reprepare. The complete batch has a 10-second drain deadline. Writes remain synchronous, and failed pipelines are never replayed.

The recorded timing runs used different run IDs, hence independently sampled random trajectories. They are order-paired samples of the same workload distribution, not identical request traces. The newer harness uses a shared deterministic RNG ID per round/load/phase for future measurements.
