# Nelua + epoll + PostgreSQL

Front: direct

Conduit's application logic is Nelua: all 19 API operations, routing, parameterized
SQL, validation, response objects, and JSON emission. It compiles to native C
using [official Nelua](https://github.com/edubart/nelua-lang), pinned
to `a58450563e2d2ec49bff499865c8b5cfdf6ff81a`.

A native host supplies epoll sockets, request-owned buffers, libpq, OpenSSL 3,
and bcrypt. The build targets GCC 13 and Ubuntu 24.04's development packages;
libpq follows the benchmark's PostgreSQL packages, discovered with `PG_CONFIG`.
The executable has no Lua VM, Nelua GC, Nelua allocator, or Nelua initialization/
panic path. Normal C allocation serves live requests.

JSON string emission skips ordinary text eight bytes at a time using bounded,
unaligned-safe word loads. Control characters, quotes, and backslashes retain
the scalar escape path; UTF-8 bytes pass through unchanged.

Measured results and reproduction: [BENCHMARKS.md](BENCHMARKS.md).

## Build and run

On Ubuntu 24.04, from the repository root:

```sh
bash submissions/nelua-epoll-spaceghost/install.sh # install packages once, as root
bash submissions/nelua-epoll-spaceghost/build.sh
bash test/run.sh submissions/nelua-epoll-spaceghost
```

The official runner requires the challenge seed, Go, psql, curl, and PostgreSQL
test credentials; see [test/run.sh](../../test/run.sh). The build verifies a clean
compiler checkout or linked worktree at the pin, generates C afresh with
`--no-cache` into the submission build directory, links companion C sources explicitly, strips unused
symbols, and audits generated C for runtime imports. No binaries are committed.
An existing compiler checkout at another revision is rejected; set `NELUA_ROOT`
to a clean checkout at the official pin when reusing a workspace from the fork build.

`start.sh` runs in the foreground. Set `DATABASE_URL` and `JWT_SECRET`; `HOST`
and `PORT` default to `127.0.0.1:3000`. Direct hosting uses `0.0.0.0:80`;
the runner supplies descriptor limits and permission to bind port 80. On a
higher port, runtime needs no root privileges, kernel changes, or extra services.

## Concurrency and database work

One epoll thread owns sockets; idle keep-alive connections retain no buffers.
Three bounded lanes own **20 PostgreSQL connections** by default: four read,
eight mutation, and eight authentication workers. Bcrypt stays off the epoll
thread. Pending work, memory, headers, bodies, and output are bounded; overload
receives 503. Idle keep-alive timeout is 75 seconds.

One collector gathers at most 128 reads from the oldest enqueue time. With spare
read workers, it uses a 2 ms window. If every other read worker is executing a
batch, it keeps the 8 ms window. It releases collection before database work. Other read workers execute
completed batches concurrently. Article, profile, comment, tag, and page/count
lookups share SQL and deduplicate keys within that batch. Viewer-specific flags
use each request's independently verified token; ordinality maps results back
to requests. Shared data and rendered responses end with the batch. Each frozen
tag group executes a fresh query, renders once, and copies bytes into each
request's independently owned response buffer; later arrivals cannot reuse it.

After every token and pagination argument has been checked independently,
identical effective reads in the frozen group share a query row and JSON rendering.
The identity includes the route family, decoded resource/filter key, verified
viewer ID, limit, and offset. Responses are copied into independently owned
buffers before the group ends, including missing-resource and error responses.
A bounded 256-slot lookup also shares viewer-independent article JSON fragments
within each page-query result, while both personal flags are read separately
from every viewer's own row. Fragment references use offsets into request-owned
buffers, are resolved after buffer growth, and expire with that result. Hash
probes are capped at 16; collisions fall back to ordinary rendering. No read or
rendered bytes survive into a later group.

A bounded libpq pipeline submits at most nine batch-read families before waiting
for results, with a 10-second deadline for flushing and draining the pipeline.
Failed pipelines are not replayed; the connection resets before its next operation.
Writes retain their synchronous commit path.

Statements are parameterized and prepared per connection. Binary PostgreSQL
results avoid text conversion for numeric values, booleans, timestamps, and
arrays. Article queries select a bounded page before enrichment. Before walking a far
offset, they compare it with the span between the smallest and largest article
IDs. An offset outside that safe upper bound produces an empty page immediately;
the fresh, capped count still runs. Numeric arithmetic keeps this valid across
the full signed 64-bit ID range, including gaps and negative IDs. Session-only
settings disable JIT and parallel gather workers and use UTC. The schema and
database-wide settings stay untouched; no extensions or external cache are used.

| Variable | Default | Purpose |
| --- | ---: | --- |
| `DB_READ_THREADS` | 4 | Read workers/connections |
| `DB_WRITE_THREADS` | 8 | Mutation workers/connections |
| `DB_AUTH_THREADS` | 8 | Login, registration, password-change workers/connections |
| `READ_GATHER_SERIAL` | 1 | Single collector; DB execution stays concurrent |
| `READ_GATHER_ADAPTIVE` | 1 | Use 2 ms with spare read workers; retain 8 ms when the others are busy |
| `READ_PIPELINE` | 1 | Bounded batch-local libpq read pipeline |
| `READ_COALESCE` | 1 | Share identical reads and public article JSON within the frozen batch |
| `READ_BATCH_STATS` | 0 | Aggregate density/wait statistics at shutdown |
| `NELUA_ROOT` | `.deps/nelua` | Clean checkout of the pinned compiler |
| `PG_CONFIG` | `pg_config` | Build-time libpq discovery |
| `JOBS` | 2 | Compiler bootstrap jobs |
| `NATIVE_FLAGS` | `-march=native` | CPU flags; set empty for a portable build |

Worker counts must be positive and total at most 95. Set `READ_GATHER_SERIAL=0`
or `READ_GATHER_ADAPTIVE=0` or `READ_PIPELINE=0` or `READ_COALESCE=0` to disable the corresponding strategy for comparison.

## Correctness

Every authenticated request verifies HS256, signature, expiry, and a positive
decimal subject. Worker-local OpenSSL HMAC contexts retain only configuration
key material and keyed provider state. Every call reinitializes the context,
hashes the current token and verifies its signature; secret changes rekey it,
and cryptographic failures discard its state. Login checks the stored bcrypt hash; registration and password
changes compute **cost 10** with fresh random salts. Interleaving up to eight
independent bcrypt states shares execution resources while completing every
password's work. Libxcrypt handles compatibility cases and supplies an independent
test oracle. Passwords over 72 bytes are rejected.

JWT verifications and password results are never retained across requests.
Read results and rendered bytes live only within the frozen batch described above.
Writes finish committing before queuing a response; synchronous
commit stays enabled and ambiguous failed commits are not retried. HTTP framing
and JSON checks cover conflicting lengths, invalid escapes, Unicode, embedded
NUL, nesting, and response size limits.

## Additional checks

From the submission directory:

```sh
python3 tests/request_test.py
python3 tests/auth_state.py --sanitize
python3 tests/tags_batch.py --sanitize
python3 tests/serialize_scan.py --sanitize
python3 tests/transport_gather.py --sanitize
DATABASE_URL='dbname=postgres' python3 tests/read_pipeline.py --sanitize
createdb nc_batch_validation
DATABASE_URL='dbname=nc_batch_validation' python3 tests/batch_sql.py
DATABASE_URL='dbname=nc_batch_validation' python3 tests/read_coalesce.py --sanitize
dropdb nc_batch_validation
BASE_URL=http://127.0.0.1:3000 python3 tests/edge_http.py
```

Request tests independently check JWT/HMAC, bcrypt, JSON, and HTTP boundaries.
Gather tests cover both modes, concurrent execution, and shutdown with pending
work. Pipeline tests need a PostgreSQL test server and use literal SELECTs to
check ownership, errors, timeouts, and recovery. Batch SQL tests replace rows in
the disposable `nc_batch_*` database and compare against independent SQL oracles.
HTTP edge tests require a running disposable application. Official rankings
require the maintainer's full-seed benchmark; local runs establish no score.

## Credits

Batching draws on [rust-epoll-WorriedArrow](../rust-epoll-WorriedArrow),
[c-epoll-umitaltintas](../c-epoll-umitaltintas), and
[csharp-sockets-jh-d](../csharp-sockets-jh-d). `src/bcrypt.c` and `src/bf_tables.h`
adapt Ümit Altıntaş's interleaved kernel from `c-epoll-umitaltintas`, snapshot
`d373e0dd994f4683a94c783627078431561d07f6`; its MIT notice is retained in
[src/BCRYPT-LICENSE](src/BCRYPT-LICENSE). This submission uses the repository's
MIT license, copyright 2026 arjaythedev and the challenge contributors.
