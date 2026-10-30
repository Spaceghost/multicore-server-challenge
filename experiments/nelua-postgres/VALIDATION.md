# Development validation — 2026-10-30

Compiler: Spaceghost/nelua-lang
`3c29419776dfdca194fa7e9c572498264fe5c654`.
Host: Linux x86-64, GCC 13.3.0, PostgreSQL 18.0.

| Check | Result |
| --- | --- |
| Build from the pinned Nelua fork | Passed |
| Runtime/import/export/constructor audit | Passed, including the installed stripped library |
| JSON, UTF8, control-byte, nullable-field, and serializer-layout tests | Passed |
| Int64 boundaries and 10,000 randomized integer cases | Passed |
| Standalone kernel ASan/UBSan | Passed |
| PostgreSQL integration and independent SQL JSON parity | 73 checks passed |
| Prepared page-query benchmark output parity | Passed |
| Python compilation, shell syntax, workflow YAML/shell syntax, whitespace checks | Passed |

The integration run used the stripped installed module. Checks cover every
implemented entry point, count/pagination limits, filter precedence, newest-first
ordering, all PostgreSQL-permitted ASCII control bytes, Unicode, toasted text,
pre-2000 UTC timestamps, injection inputs, plan reuse, invoker permissions,
idempotent concurrent writes, and caller rollback.

## Binary footprint

`make install-strip` produced a **40,104-byte** shared library in this build.
Its `.text` section was 13,551 bytes; SQL and other read-only data accounted for
8,528 bytes. The standalone optimized Nelua serializer object measured 2,664
bytes of code and zero data/BSS before cross-module LTO/inlining.

The dynamic dependency is libc; allocation, SPI execution, timestamp decoding,
errors, and cancellation use PostgreSQL symbols supplied by the host. There is
no Lua VM, GC, Nelua allocator, main entrypoint, constructor/destructor section,
or Nelua panic/exit path. There are exactly 17 exported PostgreSQL entry symbols:
module magic, eight functions, and their eight function-info records.

## Page microbenchmark

The [raw report](bench/development-2026-10-30.md) records three alternating
three-second runs per case after warm-up, one client/thread, prepared protocol,
and an independent JSON-parity check. Dataset: four users, 1,105 articles,
1,108 favorites, 137 comments, five tags, and two follows.

| Ten-article global page with capped count | Median TPS | Median average latency |
| --- | ---: | ---: |
| Native Nelua module | 1,709.38 | 0.585 ms |
| Equivalent page-first SQL JSON builders | 1,448.58 | 0.690 ms |

Observed throughput ratio: **1.180×**. This is a short development
microbenchmark on shared hardware and a small fixture. It does not establish
full-seed performance, HTTP throughput, multicore scaling, or a leaderboard score.

## Test environment limitation

The execution environment prohibits changing UID and Unix socket creation.
For these local tests only, PostgreSQL was built in scratch with its root-start
guards disabled in `initdb`, `pg_ctl`, and backend startup. The SQL executor,
SPI, memory manager, WAL, and module ABI were unmodified. The disposable server
listened on loopback TCP. No such source patch or runtime workaround is included
in this repository. The dedicated CI workflow builds unmodified, checksum-pinned
PostgreSQL source and runs as the normal GitHub Actions user.

The complete challenge HTTP conformance suite and the full workload were not run:
this module exposes eight SQL data operations rather than an HTTP application,
and database extensions are explicitly outside the challenge's rules.
