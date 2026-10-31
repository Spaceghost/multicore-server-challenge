# Full six-entry CI diagnostic shootout

[Workflow run 41148898736](https://github.com/Spaceghost/multicore-server-challenge/actions/runs/41148898736), candidate `2a07dab2445432f908297a782876d1c851cab137`, harness snapshot `1a97e10df48a4ed734640bf72df8a62ca8ae6d7a`. Only Nelua and the frozen published top five are included.

All six original install/build scripts succeeded, all six entries passed 197/197 conformance, and all 24 measurements passed the latency/error thresholds with **zero application errors**. Maximum observed database connections: 20. **16/24 measurements are eligible**: all 12 at 1000 users, plus RustCat and Zig at 5000 users. Eight high-load rows exceed the shared host CPU threshold. **No capacity winner or official score is established.**

Two rounds used fresh verified full-seed clones, think scale 0.1, 10-second warm-up, 5-second ramp, 20-second measurement and 3-second tail. This is a partial balanced-order block, not six complete rounds.

## Eligible 1000-user medians

| Entry | Req/s | p95 ms | p99 ms | Host CPU | App RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| nelua-epoll-spaceghost | 2522.050 | 30.415 | 34.095 | 28.862 | 14.045 |
| rust-epoll-theCatWisel | 2559.825 | 20.551 | 22.191 | 20.133 | 6.648 |
| zig-iouring-nick-potts | 2321.575 | 91.807 | 97.503 | 19.919 | 124.369 |
| rust-epoll-WorriedArrow | 2583.175 | 18.927 | 21.815 | 21.336 | 48.646 |
| asm-epoll-nickita-khylkouski | 2613.075 | 2.128 | 3.140 | 48.153 | 8.211 |
| csharp-epoll-aot-gichamba | 2531.325 | 26.415 | 28.551 | 23.455 | 31.443 |

Nelua has lower latency than Zig at this offered load and higher latency than the other four leaders. The Rust leaders also consume much less host CPU. These comparisons describe this workload point; they do not order maximum user capacity.

At 5000 users, both Nelua, WorriedArrow, ASM and C# repetitions are flagged because whole-box CPU exceeds 75%. RustCat and Zig remain eligible there. Every high-load run still passes SLOs; the largest p99 across all 24 runs is 327.679ms. Flagged latency/CPU/error values remain in `results/runs.tsv` and raw JSON instead of being discarded.

The runner has 4 CPUs/~16GiB, PostgreSQL 18.6 and a descriptor hard limit 65,536. PostgreSQL and the load generator share the machine. This differs from the dedicated 8-vCPU/16GB official server, external clients, 200,000 descriptors and prescribed PostgreSQL configuration. Raw environment/settings/toolchains, full seed fingerprints, executable hashes, sampled memory/CPU/connections, build/conformance logs and complete loadgen output are retained here. Process metrics span ramp/measure/tail; loadgen host CPU comes from its measured interval.

The fixed persistent HTTP/1.1 readiness probe matches the official curl/Go behavior. Comparator sources remain unchanged. Earlier Python `Connection:close` readiness probes exposed a C# close-before-deferred-response path; those earlier matrices were correctly incomplete.

These measurements used different per-case RNG IDs at the recorded harness snapshot. They sample the same workload distribution with different random trajectories. The newer harness at `b78b722` shares deterministic RNG IDs per round/load/phase; 17 focused tests and two live fresh-database runs verify that behavior. No earlier data is relabeled as identical traces.

An independent artifact check verified all 287 ZIP members, the exact 24 unique slots/six names, frozen source/toolchain pins, unchanged per-case executable hashes, zero errors, eligibility flags and sampled resource aggregates. Tabular/log/JSON data is preserved as UTF8 text; the original downloadable artifact remains linked from the workflow run.
