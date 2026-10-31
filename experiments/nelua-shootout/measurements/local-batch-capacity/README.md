# Larger batch capacities: not adopted

The same pinned compiler/application source was built at capacities 128, 256 and 512. Only the transport maximum, Nelua count guard and 10 matching typed arrays change; exact patches and binary hashes are retained. No binaries are committed.

Two rounds use fresh full-seed clones and shared deterministic RNG IDs within each round: 128/256/512 then 512/256/128. Each case gets 5-second warm-up, 3-second ramp, 12-second measurement and 1-second tail, 8,000 users and think scale 0.1. These short local diagnostics do not establish an official capacity ceiling.

| Capacity | Median req/s | Median p95 ms | Median p99 ms | Median host CPU |
| --- | ---: | ---: | ---: | ---: |
| 128 | 19498.333 | 52.975 | 119.423 | 66.896 |
| 256 | 18491.500 | 86.751 | 156.351 | 61.335 |
| 512 | 17230.583 | 151.871 | 218.303 | 60.034 |

Every case has zero errors, passes SLOs, is not load-generator limited, and uses 20 database connections. Larger batches trade latency/throughput at this offered load for some CPU savings. The 256 capacity saves modest CPU per request; 512 does not do so consistently. Neither demonstrates a higher eligible user ceiling. Retain 128 as the measured default; preserve these alternatives for a future isolated capacity test rather than promoting them on CPU percentage alone.

Apply either patch to a separate checkout of candidate 2a07dab and run its unchanged build.sh to reproduce the binary. Runtime audits passed for both: no Nelua VM/GC/allocator/panic/init path. Full raw records, environment and density statistics are retained.
