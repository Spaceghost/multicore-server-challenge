# Top-five Nelua diagnostic shootout

This compares only Nelua and the frozen published top five. All values are local/CI diagnostics, not official user ceilings or a replacement for the maintainer's isolated eight-core five-minute holds.

Generated 2026-10-31T02:33:56+00:00.

Complete eligible matrix: **no**. io_uring setup probe: `available`.

Template `conduit_seed`; 500000 seeded articles; think scale 0.1; ramp 5s; warm-up 10s; measured 20s; tail 3s; 2 round(s). Six rounds complete a Williams position/carryover-balanced block; shorter runs are an explicitly partial block.

| Case | Users | Conformance | Eligible repetitions | Median req/s | p50 ms | p95 ms | p99 ms | Error rate | Peak RSS MiB |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nelua-epoll-spaceghost (default) | 1000 | pass | 2 | 2581.00 | 9.36 | 14.78 | 17.86 | 0.00 | 13.56 |
| rust-epoll-theCatWisel | 1000 | pass | 2 | 2549.27 | 15.84 | 19.97 | 21.57 | 0.00 | 6.57 |
| zig-iouring-nick-potts | 1000 | pass | 2 | 2328.25 | 52.56 | 91.07 | 96.41 | 0.00 | 124.21 |
| rust-epoll-WorriedArrow | 1000 | pass | 2 | 2567.07 | 11.06 | 18.80 | 21.54 | 0.00 | 51.87 |
| asm-epoll-nickita-khylkouski | 1000 | pass | 2 | 2635.15 | 0.57 | 1.98 | 3.02 | 0.00 | 8.15 |
| csharp-epoll-aot-gichamba | 1000 | pass | 2 | 2541.10 | 17.49 | 25.20 | 27.05 | 0.00 | 31.22 |
| nelua-epoll-spaceghost (default) | 5000 | pass | 0 | — | — | — | — | — | — |
| rust-epoll-theCatWisel | 5000 | pass | 2 | 11922.15 | 42.67 | 63.01 | 73.15 | 0.00 | 16.56 |
| zig-iouring-nick-potts | 5000 | pass | 2 | 11101.67 | 71.58 | 122.05 | 134.66 | 0.00 | 156.04 |
| rust-epoll-WorriedArrow | 5000 | pass | 1 | 12125.20 | 32.64 | 48.58 | 62.75 | 0.00 | 89.41 |
| asm-epoll-nickita-khylkouski | 5000 | pass | 0 | — | — | — | — | — | — |
| csharp-epoll-aot-gichamba | 5000 | pass | 0 | — | — | — | — | — | — |

**No shootout winner is declared.** At least one comparator/run is blocked, incomplete, failed, or load-generator limited. Missing top-five entries are never replaced with a lower-ranked comparator.

`runs.tsv` keeps failures and flagged results instead of hiding them. `environment.tsv`, `sources.tsv`, per-run logs, raw load-generator JSON, and one-second RSS/connection samples make the measurement auditable. App connection counts above 95 fail that run. Connection peaks are sampled observations, not a proof that sub-second peaks cannot occur.

Think/session time is accelerated for this diagnostic. Its virtual-user count is not comparable with official unscaled users.
