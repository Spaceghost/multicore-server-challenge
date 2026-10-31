# Catch-up v2: measured choices

Selected entry: [`bc35c96`](https://github.com/Spaceghost/multicore-server-challenge/commit/bc35c96ef444521151f6f3a78591f39b59f21b6e), pinned Nelua compiler [`4b5dfd4`](https://github.com/Spaceghost/nelua-lang/commit/4b5dfd4a76ce4f6e3c59983295f32f7db68466b4). Baseline is the previous entry `2a07dab2445432f908297a782876d1c851cab137` with compiler `3c29419776dfdca194fa7e9c572498264fe5c654`. Exact variant mapping and preserved-binary hashes are in [PROVENANCE.json](PROVENANCE.json). No binaries are included.

## Normal whole-server diagnostics

All cases use a fresh verified full-seed clone and the official workload generator at think scale 0.1, with shared deterministic IDs per round/load/phase. These are local same-host diagnostics, not official scores or maximum-capacity rankings. Baseline means the old PR, not merely the previous timer value.

| Series | Users | Variant | Median req/s | p95 ms | p99 ms | Host CPU % |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| feed ABBA | 8000 | baseline | 19406.375 | 63.519 | 135.391 | 67.211 |
| feed ABBA | 8000 | candidate | 19385.400 | 61.023 | 153.151 | 68.918 |
| host/heap | 8000 | baseline | 19397.050 | 59.247 | 129.663 | 67.787 |
| host/heap | 8000 | host | 19342.925 | 74.207 | 145.471 | 66.963 |
| host/heap | 8000 | allocator | 19295.650 | 77.007 | 155.039 | 67.859 |
| selected combo | 1000 | baseline | 2502.000 | 30.255 | 58.511 | 13.524 |
| selected combo | 1000 | window8 | 2569.300 | 15.479 | 28.487 | 15.135 |
| selected combo | 8000 | baseline | 19428.633 | 68.863 | 127.487 | 65.691 |
| selected combo | 8000 | window8 | 19646.033 | 46.687 | 111.391 | 65.611 |

All 18 runs have zero application errors, pass the latency/error SLOs, remain below the load-generator CPU limitation threshold, and peak at 20 database connections. CPU is the whole host, including PostgreSQL and the generator; process CPU/RSS is unavailable because procfs and system-call PID namespaces differ. Exact unrounded observations and full raw logs/JSON are under `whole-server/`.

The feed and host/heap series use a 10-second warm-up (3-second ramp), then a 5-second ramp, 20-second measurement and 3-second tail. The selected-combination series uses a 5-second warm-up (3-second ramp), then a 3-second ramp, 15-second measurement and 1-second tail. Both round orders reverse the compared variants. Short repeats vary; do not treat these as searched ceilings.

Variant meanings:

- **Feed ABBA:** `candidate` adds tag rendering once per pending batch, reusable per-thread HMAC key state, and the feed-hub query, with the original 20 ms gather window. The SQL microbenchmark win did not yield a repeatable whole-server win: median throughput is slightly lower, p99 and host CPU are higher. **Feed hubs were rejected.**

- **Host/heap:** `host` contains only tag/HMAC changes with a 20 ms window; `allocator` adds app-local mimalloc 3.3.2. The allocator gain changes direction between rounds and its medians do not justify another heap dependency. **Mimalloc was rejected.** Its pinned source recipe and ownership test are retained under `rejected/mimalloc/`. Shared libraries kept their original allocators; no preload/global replacement was used.

- **Selected combination:** `window8` contains tag/HMAC changes plus the 8 ms gather window. Compared with the old PR, median p95 falls 48.84% at 1,000 users and 32.20% at 8,000 users; throughput rises 2.69% and 1.12%. Low-load host CPU rises from 13.52% to 15.13%, while high-load CPU is approximately unchanged. This is a **combined optimization**, not an isolated measurement of changing 20 ms to 8 ms.

## Components and toolchain

The [tags log](components/tags/tags-batch-abba.log) measures actual request creation, generated batch rendering and owned-response cleanup against fresh in-memory libpq results: 200 tags × 128 requests × 200 batches per run. Median component CPU is 0.218231→0.016743 seconds (−92.33%) for identical 51,456,000 response bytes. Wrappers disable LTO so the mock/query and decode counters remain reliable; this is not an application/leaderboard gain. The frozen test sources accompany the log. Build separate baseline/selected checkouts, then run the selected submission's `tests/tags_batch.py --baseline-app /path/to/baseline/build/app.c --benchmark 200` with `PG_CONFIG` selecting libpq.

The HMAC [recovered session samples](components/hmac/recovered-session-samples.json) report approximately 35.30% lower request-boundary CPU, recomputing every signature across a diverse corpus. These rounded numbers were recovered from the recorded session summary, not an original raw log. The standalone source/reproducer is retained: from `components/hmac/`, run `python3 tools/bench-auth.py --baseline-source baseline-request.c` using OpenSSL 3, a C compiler, libxcrypt and pthreads. It caches key-derived state, not JWTs or verification results. These component gains were not promoted as normal-workload throughput percentages.

The compiler change fixes stale cached binaries after imported C/C++ companion sources or relevant compiler/strip flags change. It changes no language or optimization defaults. [GCC](toolchain/cache-final-gcc.log) and [Clang](toolchain/cache-final-clang.log) each pass 511 tests; the [old compiler regression](toolchain/cache-baseline-regression.log) shows the expected stale result (4 instead of 5). For the selected app, old/new compiler output is byte-identical: 79,645 bytes, SHA256 `3a7c1cdc5c81396f9994de3b5ad3b08d0e410cbdd45ca5ad9c6e670b61efd603`. No runtime speedup is attributed to the cache fix. Transitive headers/libraries remain outside its direct-source fingerprint; use `--no-cache` after those change.

## Reproduction and limits

The feed prototype keeps the SQL, exact array inputs, plans and ten binary-row parity cases. Its component timings improved 23–45% for larger feed batches, but the normal-workload evidence above governs rejection. `DATABASE_URL` must select an immutable full seed; use `python3 rejected/feed-hubs/reproduce.py --output /new/empty/output --libpq /path/to/libpq.so` for parity/plans, optionally `--benchmark --seconds 1`. This wrapper preserves the original evidence and writes new plans separately. The original generator/driver source is retained unchanged.

The allocator recipe uses `libmimalloc-sys 0.1.49`, containing mimalloc 3.3.2; archive SHA256 `6a45a52f43e1c16f667ccfe4dd8c85b7f7c204fd5e3bf46c5b0db9a5c3c0b8e9`. In an isolated selected checkout, apply `rejected/mimalloc/host20.patch`, copy its `tools/` and `tests/` files into the submission, run the unchanged `build.sh`, then `bash tools/build-allocator.sh mimalloc`. The recipe fetches/validates source and redirects only the native app's four heap functions. It is preserved as a rejected experiment, not an entry dependency.

**Local-environment deviation:** the earlier diagnostics in this folder ran with UID 0 and a scratch PostgreSQL 18.0 build whose root-start guard was disabled; no executor/MVCC change or such patch is in the entry. The sandbox has an 8-core quota/~8 GiB, descriptor hard limit 16,384, stock PostgreSQL settings and a co-located generator. These differ from the official ordinary-user service, dedicated 8-vCPU/16-GB box, external clients and 200,000 descriptors. The latest top-five snapshot is retained in `current-top-five.json`; no lower-ranked competitor was substituted.

The new [optional 300-second hold](stability/README.md) is **blocked with no measurement**: the sandbox maps only UID/GID 0, denies switching to an ordinary user, and has no capabilities to create a compliant mapping. Its guarded driver and complete preflight are retained; PostgreSQL/app/loadgen were not started. No 300-second metrics for the selected head are invented. See [RULES.md](RULES.md) for the selected-entry audit. No new all-five CI data is included in this archive snapshot.
