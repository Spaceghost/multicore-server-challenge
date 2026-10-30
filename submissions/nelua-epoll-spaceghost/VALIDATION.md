# Validation — 2026-10-30

This is a complete standalone HTTP entry, separate from the PostgreSQL extension
and XDP experiments. Its application, routes, SQL, validation, and response
serialization compile from Spaceghost's Nelua fork at
`3c29419776dfdca194fa7e9c572498264fe5c654`.

| Check | Result |
| --- | --- |
| Official HTTP conformance on development seed | 197/197 passed |
| Official `test/run.sh` on full reference seed, after SQL/bcrypt tuning | 197/197 passed |
| Actual emitted batch SQL vs independent SQL oracles | 91 assertions passed |
| Concurrent read differential against unchanged C comparator on full seed | 1,000 paired reads, no mismatches |
| HTTP framing/auth/Unicode/idle-socket edge checks | 20 checks passed |
| Independent request boundary/HMAC/JWT/bcrypt tests | Passed |
| Interleaved bcrypt vs libxcrypt | 108 cost-10 vectors across lanes 1–8 passed |
| Concurrent bcrypt coordinator | 16 jobs, positive/negative verification and fallback guards passed |
| ASan/UBSan request parser and bcrypt/coordinator stress | Passed |
| Generated Nelua runtime audit | Passed |
| Python/shell compilation and source whitespace checks | Passed |

The differential run verifies real favorite/follow edges and known nonedges,
including repeated keys with opposite viewers. SQL oracle tests cover all nine
batched read families, overlapping page/count keys, missing resources/filters,
empty comment threads, newest-100 ordering, Unicode/controls, capped counts,
and maximum int64 offsets. Request framing tests include pipelining, partial
bodies, half-close, conflicting lengths, transfer encoding rejection, URL
escapes, and recovery after malformed traffic.

## Measured tuning

Generic plans originally estimated a materialized flags table at one row,
then rescanned its actual 320 rows 320 times. Replacing that join with direct
indexed flag probes removed the quadratic work. Four alternating warm
32-request EXPLAIN/ANALYZE probes on the full seed measured:

| Batch family | Before | After |
| --- | ---: | ---: |
| Global page | 8.857 ms | 2.151 ms |
| Tag page | 11.031 ms | 3.109 ms |
| Favorited page | 9.561 ms | 2.665 ms |
| Feed | 22.066 ms | 15.423 ms |

These are query execution probes, not end-to-end application speedups.
The independent optimized bcrypt check measured 56.74 ms CPU/hash through
libxcrypt versus 18.00 ms/hash with eight interleaved lanes, about 3.15× hash
throughput per CPU. Every hash still performs cost 10 with its own state/salt.

## Full-dataset mixed workload

The [complete local report](benchmarks/local-2026-10-30.md) includes raw endpoint
summaries and the C comparator. The selected four-read-worker configuration
handled **21,573.5 requests/s**, p95 **139.3 ms**, p99 **178.0 ms**, and **zero
errors** over a twenty-second measured window with 10,000 accelerated local
virtual users. Whole-host CPU averaged 72%; the supplied load generator did
not flag that run as limited. A six-reader trial improved latency/throughput
but raised shared-host CPU enough to trigger that flag, so four stays default.

The C comparator remained faster in these short runs. No leaderboard win,
official user ceiling, or five-minute hold is claimed. Think/session time was
accelerated by 0.1, the load generator shared the host, and the development
cluster used 128 MB shared buffers rather than the official box configuration.
The full seed itself passed the stock row-count/content fingerprints and
occupied 3,560 MB. Default connections total 20: four read, eight write, eight
auth; the independent bcrypt compute thread opens no PostgreSQL connection.

The stripped executable is **390,304 bytes** on the recorded GCC 13.3/x86-64
build. That is the executable file size, excluding shared system libraries.
The generated Nelua has no VM, GC, allocator, panic path, or initialization
entrypoint. Native C memory management, libpq, OpenSSL, and libxcrypt remain
explicit dependencies.

## Local runtime limitation

The workspace prohibits UID changes and Unix sockets. Local PostgreSQL 18.0
tests therefore used loopback TCP and a scratch build with only its root-start
guards disabled. SQL, SPI, MVCC, WAL, and the executor were unmodified; no such
patch or workaround is included in the submission. Stock PostgreSQL 18 CI is
the independent check on the normal server/runtime. This submission needs no
extra capabilities beyond the contest's port-binding grant and creates no
database objects or privileged networking setup.
