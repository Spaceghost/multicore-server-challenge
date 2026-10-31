# Top-five Nelua diagnostic shootout

This compares only Nelua and the frozen published top five. All values are local/CI diagnostics, not official user ceilings or a replacement for the maintainer's isolated eight-core five-minute holds.

Generated 2026-10-31T00:15:33+00:00.

Complete eligible matrix: **no**. io_uring setup probe: `blocked: errno=1 Operation not permitted`.

Template `conduit_seed`; 500000 seeded articles; think scale 0.1; ramp 5s; warm-up 10s; measured 20s; tail 3s; 2 round(s). Six rounds complete a Williams position/carryover-balanced block; shorter runs are an explicitly partial block.

| Case | Users | Conformance | Eligible repetitions | Median req/s | p50 ms | p95 ms | p99 ms | Error rate | Peak RSS MiB |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nelua-epoll-spaceghost (baseline) | 8000 | pass | 2 | 18938.03 | 37.81 | 93.02 | 155.90 | 0.00 | 0.00 |
| nelua-epoll-spaceghost (tuned) | 8000 | pass | 2 | 19514.15 | 29.13 | 61.61 | 133.98 | 0.00 | 0.00 |
| rust-epoll-theCatWisel | 8000 | pass | 2 | 18797.88 | 48.35 | 66.62 | 127.10 | 0.00 | 0.00 |
| zig-iouring-nick-potts | 8000 | blocked: io_uring unavailable | 0 | — | — | — | — | — | — |
| rust-epoll-WorriedArrow | 8000 | pass | 2 | 19353.97 | 34.34 | 51.78 | 104.16 | 0.00 | 0.00 |
| asm-epoll-nickita-khylkouski | 8000 | pass | 0 | — | — | — | — | — | — |
| csharp-epoll-aot-gichamba | 8000 | blocked/failed: RuntimeError | 0 | — | — | — | — | — | — |

**No shootout winner is declared.** At least one comparator/run is blocked, incomplete, failed, or load-generator limited. Missing top-five entries are never replaced with a lower-ranked comparator.

`runs.tsv` keeps failures and flagged results instead of hiding them. `environment.tsv`, `sources.tsv`, per-run logs, raw load-generator JSON, and one-second RSS/connection samples make the measurement auditable. App connection counts above 95 fail that run. Connection peaks are sampled observations, not a proof that sub-second peaks cannot occur.

Think/session time is accelerated for this diagnostic. Its virtual-user count is not comparable with official unscaled users.
