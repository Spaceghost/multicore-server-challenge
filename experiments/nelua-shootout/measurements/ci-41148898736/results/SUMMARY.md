# Top-five Nelua diagnostic shootout

This compares only Nelua and the frozen published top five. All values are local/CI diagnostics, not official user ceilings or a replacement for the maintainer's isolated eight-core five-minute holds.

Generated 2026-10-31T00:42:00+00:00.

Complete eligible matrix: **no**. io_uring setup probe: `available`.

Template `conduit_seed`; 500000 seeded articles; think scale 0.1; ramp 5s; warm-up 10s; measured 20s; tail 3s; 2 round(s). Six rounds complete a Williams position/carryover-balanced block; shorter runs are an explicitly partial block.

| Case | Users | Conformance | Eligible repetitions | Median req/s | p50 ms | p95 ms | p99 ms | Error rate | Peak RSS MiB |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nelua-epoll-spaceghost (default) | 1000 | pass | 2 | 2522.05 | 21.08 | 30.41 | 34.09 | 0.00 | 14.04 |
| rust-epoll-theCatWisel | 1000 | pass | 2 | 2559.82 | 16.00 | 20.55 | 22.19 | 0.00 | 6.65 |
| zig-iouring-nick-potts | 1000 | pass | 2 | 2321.57 | 53.04 | 91.81 | 97.50 | 0.00 | 124.37 |
| rust-epoll-WorriedArrow | 1000 | pass | 2 | 2583.18 | 11.28 | 18.93 | 21.81 | 0.00 | 48.65 |
| asm-epoll-nickita-khylkouski | 1000 | pass | 2 | 2613.07 | 0.63 | 2.13 | 3.14 | 0.00 | 8.21 |
| csharp-epoll-aot-gichamba | 1000 | pass | 2 | 2531.32 | 18.47 | 26.41 | 28.55 | 0.00 | 31.44 |
| nelua-epoll-spaceghost (default) | 5000 | pass | 0 | — | — | — | — | — | — |
| rust-epoll-theCatWisel | 5000 | pass | 2 | 11829.48 | 45.98 | 66.37 | 77.41 | 0.00 | 16.21 |
| zig-iouring-nick-potts | 5000 | pass | 2 | 11093.03 | 72.57 | 123.78 | 135.94 | 0.00 | 155.87 |
| rust-epoll-WorriedArrow | 5000 | pass | 0 | — | — | — | — | — | — |
| asm-epoll-nickita-khylkouski | 5000 | pass | 0 | — | — | — | — | — | — |
| csharp-epoll-aot-gichamba | 5000 | pass | 0 | — | — | — | — | — | — |

**No shootout winner is declared.** At least one comparator/run is blocked, incomplete, failed, or load-generator limited. Missing top-five entries are never replaced with a lower-ranked comparator.

`runs.tsv` keeps failures and flagged results instead of hiding them. `environment.tsv`, `sources.tsv`, per-run logs, raw load-generator JSON, and one-second RSS/connection samples make the measurement auditable. App connection counts above 95 fail that run. Connection peaks are sampled observations, not a proof that sub-second peaks cannot occur.

Think/session time is accelerated for this diagnostic. Its virtual-user count is not comparable with official unscaled users.
