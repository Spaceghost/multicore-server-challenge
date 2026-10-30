# Nelua + epoll + libpq

Front: direct

A complete Conduit HTTP/1.1 application written in Nelua, compiled to native C
with [Spaceghost's fork](https://github.com/Spaceghost/nelua-lang) pinned at
`3c29419776dfdca194fa7e9c572498264fe5c654`.

| Component | Version/source |
| --- | --- |
| Application, routing, SQL, validation, JSON serialization | Nelua, pinned fork above |
| HTTP transport and bounded worker queues | Linux epoll, native C host in `src/transport.c` |
| PostgreSQL driver | libpq, Ubuntu 24.04/benchmark PostgreSQL packages; binary result protocol |
| HS256 HMAC and entropy | OpenSSL 3, Ubuntu 24.04 `libssl-dev` |
| bcrypt cost 10 | interleaved native kernel with libxcrypt fallback; `src/BCRYPT-LICENSE` |
| Native compiler | GCC 13, Ubuntu 24.04 `build-essential` |

`install.sh` installs the system development packages. `build.sh` fetches and
verifies the pinned fork, generates C, links one executable, strips unused
symbols, and audits generated code and runtime imports. `start.sh` executes the
server in the foreground. No prebuilt binaries are committed.

```sh
bash submissions/nelua-epoll-spaceghost/install.sh # once, as root
bash test/run.sh submissions/nelua-epoll-spaceghost
```

The application reads `DATABASE_URL`, `JWT_SECRET`, `HOST`, and `PORT`. Direct
hosting uses `HOST=0.0.0.0 PORT=80`; local testing can use `127.0.0.1:3000`.
The service runner supplies descriptor limits and permission to bind port 80.

## Runtime and concurrency

Nelua owns the application logic: all 19 API operations, parameterized SQL,
validation, response objects, and JSON string/integer emission. A small native
host exposes sockets, libpq, OpenSSL, libxcrypt, binary value decoding, and
request-owned buffers through a typed C ABI. There is no Lua VM, Nelua GC,
Nelua allocator, or Nelua initialization/panic path in the executable. Ordinary
C allocation belongs to the host and remains necessary for live requests.

One epoll thread owns all sockets. Idle keep-alive connections retain no input
or output buffers. Requests run on three bounded lanes, each worker owning one
PostgreSQL connection; bcrypt never blocks the epoll thread. Defaults are
four read workers, eight write workers, and eight authentication workers: **20
connections total**. Queues and input memory are bounded; overload returns 503
rather than retaining unbounded work. Descriptor exhaustion pauses acceptance
and recovers without restarting the server. Keep-alive idle timeout is 75 s.

| Optional variable | Default | Meaning |
| --- | ---: | --- |
| `DB_READ_THREADS` | 4 | read workers/connections |
| `DB_WRITE_THREADS` | 8 | mutation workers/connections |
| `DB_AUTH_THREADS` | 8 | login, registration, and password-change workers/connections |
| `NELUA_ROOT` | `.deps/nelua` | clean checkout of the pinned compiler, for building |
| `PG_CONFIG` | `pg_config` | build-time libpq header/library discovery |
| `JOBS` | 2 | compiler bootstrap build jobs |
| `NATIVE_FLAGS` | `-march=native` | native compiler CPU flags; set empty for portable builds |

Worker counts must be positive, and their sum must not exceed 95. No kernel
settings, affinity, database-wide settings, or other processes are changed.

## Database work

Every statement is parameterized and prepared per connection. Result values use
PostgreSQL's binary protocol, keeping counts, booleans, timestamps, and text
arrays out of a textual conversion round trip. Article lists select a bounded
page of IDs before enrichment and return their capped count in the same query.
Comments distinguish an unknown article from an empty thread in one query.

The read lane gathers requests already waiting for up to 20 ms, at most 128 per
batch. Article, profile, comment, and tag reads share SQL work within that batch;
article/profile/comment keys are deduplicated before lookup and enrichment.
Global, tag, author, favorited, and feed pages also share distinct page and
count keys; each distinct article is enriched once per batch kind, and flags
use indexed per-request lookups. A materialized flags join was deliberately
removed after a generic-plan underestimate caused quadratic rescans.
Viewer-specific flags follow each request's independently verified token.
Ordinality maps results back to their request. No data or rendered response
survives a completed batch. Current-user reads retain their individual handler.

Connections disable JIT and parallel gather workers, use UTC, and set only their
own session parameters. The driver disables unnecessary TLS for local PostgreSQL
connections. There are no new tables, indexes, views, functions, triggers,
extensions, external caches, or changes to the fixed schema.

## Correctness

Every authenticated request verifies its HS256 signature, algorithm, expiry,
and positive decimal subject. Login checks the stored bcrypt hash; registration
and password changes use cost 10 and fresh random salts. Passwords above
bcrypt's 72-byte limit are rejected rather than silently truncated. No JWT
verification, password result, query result, or response is cached across
requests.

One bounded compute queue interleaves up to eight independent bcrypt states,
using the existing challenge implementation credited below. Every lane performs
the complete cost-10 computation; this shares execution resources, not password
results. A short five-millisecond gather bounds lone-request batching delay.
The API accepts cost-10 bcrypt hashes; unsupported accelerated settings and
legacy high-bit `$2a$` cases use libxcrypt. Normal bio/email edits use the write lane and never queue behind
password hashes.

Writes finish their PostgreSQL commit before the HTTP response is queued.
Article creation uses an explicit transaction; other statements complete their
normal autocommit. Synchronous commit is not disabled. Ambiguous failed commits
are not retried. Errors use the RealWorld `errors.body` envelope; timestamps are
UTC with exactly three fractional digits, truncated rather than rounded.

The HTTP boundary bounds headers and bodies and rejects conflicting content
lengths, transfer encoding, invalid escapes, and embedded NUL at C-string/text
boundaries. JSON keys are case-sensitive and duplicate keys use their last value.

## Checks and measurements

The official conformance command is shown above. Additional checks are:

```sh
python3 submissions/nelua-epoll-spaceghost/tests/request_test.py
BASE_URL=http://127.0.0.1:3000 python3 submissions/nelua-epoll-spaceghost/tests/edge_http.py
# With two servers on the same immutable seed, compare 1,000 concurrent reads:
BASE_URL=http://127.0.0.1:3000 REFERENCE_URL=http://127.0.0.1:3001 \
  python3 submissions/nelua-epoll-spaceghost/tests/differential.py
```

The boundary tests independently check Python-generated HMAC/JWT vectors,
bcrypt cost/salts, Unicode/control escaping, HTTP framing, and response bounds.
`tests/request_sanitize.c` provides an ASan/UBSan parser stress driver. Run the
HTTP edge checks against a disposable test instance. Official rankings require
the maintainer's full-seed benchmark; local measurements do not establish a
leaderboard score.

After building, `tests/batch_sql.py` checks the actual emitted batch SQL against
independent SQL oracles in a disposable `nc_batch_*` database. The reset guard
rejects ordinary application database names. `tools/local-bench.sh` clones a
seed and runs the supplied mixed-workload load generator; optional `TEMPLATE`,
`ARTICLES`, `USERS`, `MEASURE`, and `THINK_SCALE` select the local run. Full-seed
testing uses `TEMPLATE=conduit_seed ARTICLES=500000`. The load generator shares
the host in these checks, so their results are development evidence only.

## Credits

Read batching and work sharing follow the published designs of
[rust-epoll-WorriedArrow](../rust-epoll-WorriedArrow),
[c-epoll-umitaltintas](../c-epoll-umitaltintas), and
[csharp-sockets-jh-d](../csharp-sockets-jh-d). Page-first bounded queries, binary
results, and direct epoll hosting follow the challenge's reference schema and
the performance analyses shared by its contributors. The implementation is
provided under the repository's MIT license.

`src/bcrypt.c` and `src/bf_tables.h` adapt the interleaved kernel from
[c-epoll-umitaltintas](../c-epoll-umitaltintas), with its MIT license retained in
`src/BCRYPT-LICENSE`. The bounded synchronous coordinator and host integration
are specific to this submission; libxcrypt remains the independent test oracle
and compatibility fallback.
