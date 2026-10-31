# Shootout evidence

The submission remains one commit, bc35c96, in [PR #146](https://github.com/arjaythedev/multicore-server-challenge/pull/146). The previous 2a07dab baseline is preserved on `codex/nelua-baseline-2a07dab`. These research records compare only Nelua with the frozen top five; native/SQL ablations compare our own variants. No official capacity winner is claimed.

| Evidence | Outcome |
| --- | --- |
| [Selected catch-up changes and raw diagnostics](catchup-v2/README.md) | Batch-local tag rendering, per-message HMAC verification with reusable key setup, and an 8 ms gather window; paired local p95 improves at both loads. Feed and mimalloc prototypes are rejected after mixed-workload checks. |
| [Exact-head rule audit](catchup-v2/RULES.md) | All 12 rules checked against bc35c96, with fixed source links, accepted batching precedents and explicit diagnostic limitations. Upstream green CI uses the dev seed; full-seed validation is separate. |
| [Paired all-six CI for bc35c96](ci-41158333666/README.md) | Six original builds and six explicit full-seed 197/197 passes; 24/24 measurements and zero errors, 17 eligible and 7 CPU flags. At 1000 users Nelua has lower p95/p99 than four leaders; ASM is faster. Both Nelua 5000-user runs are CPU-flagged and trail all five on latency. |
| [Previous all-six CI matrix](ci-41148898736/README.md) | Six original builds and six 197/197 conformance passes; 24/24 measurements complete and SLO pass with zero errors; 16 eligible, 8 whole-host CPU flags. The earlier 2a07dab baseline trails four leaders on low-load latency. |
| [Local 8000-user ablation](local-8000-2026-10-30/README.md) | Serialized collection plus read pipelining improves p95 in both orders; independent random trajectories, incomplete top-five runtime coverage. |
| [Five-minute stability hold](local-five-minute-stability/README.md) | 18,779 req/s, p95 122.879 ms, p99 213.503 ms, 0.09% HTTP 503 errors; SLO pass, not load-generator limited. |
| [Batch capacities 128/256/512](local-batch-capacity/README.md) | Larger batches trade latency and delivered throughput for modest CPU savings; retain 128. Shared deterministic RNG seeds. |
| [Feed query proof](../ablations/2026-10-30-feed/README.md) | Remove a redundant follow lookup; exact binary-row parity, short SQL microbenchmark gains. Adopted. |
| [Unified-page prototype](../ablations/2026-10-30-unified-pages/README.md) | Exact parity but only ~3% normal-mix gain for more code. Not adopted. |

CI uses 4 CPUs/~16GiB and local tests have an 8-core quota/~8GiB. Both co-locate PostgreSQL and the load generator, have lower descriptor limits and use recorded stock PostgreSQL settings. The official contest uses 8 dedicated vCPUs/16GB, external clients, 200,000 descriptors, its prescribed database configuration, unscaled sessions and five-minute holds at a searched ceiling. User counts and throughput here cannot be extrapolated to that score.

The 17-test harness now pairs RNG IDs by round/load/phase. Earlier records disclose independent sampling. Original failures, eligibility flags, statuses, sampled resources, source/toolchain pins and executable hashes are retained. The live paired-ID smoke used two fresh databases and the exact same generated ID, producing 21 requests and zero errors in each; it validates plumbing, not performance. The official leaderboard was rechecked after the run and its top five still match pins.tsv.
