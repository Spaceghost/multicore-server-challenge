# Nelua inside PostgreSQL

A native PostgreSQL 18 module for Conduit's query and JSON paths, compiled with
[Spaceghost's Nelua fork](https://github.com/Spaceghost/nelua-lang) at
`3c29419776dfdca194fa7e9c572498264fe5c654`.

**This is an experiment outside the challenge rules.** README rule 3 forbids
database functions and extensions, and the benchmark role cannot install them.
This folder is deliberately outside `submissions/`. It is a SQL data plane,
not a complete HTTP server or a claim to pass the 197-step HTTP conformance suite.

## What runs where

PostgreSQL loads `nelua_conduit.so` into each ordinary backend. The C bridge
handles PostgreSQL's calling convention, prepared SPI plans, binary Datums, and
memory contexts. Nelua writes the JSON strings, integers, profiles, articles,
and comments directly into PostgreSQL-owned response buffers.

The Nelua compiler uses its bundled Lua at **build time only**. The module has:

- No Lua VM, GC, Nelua allocator, initialization entrypoint, or panic/exit path.
- No C constructors/destructors or separate runtime library.
- No response, row, authorization, or password cache. Each call reads PostgreSQL.
- No FDW, background worker, extra listener, or database connection of its own.

An FDW is for accessing foreign tables. These queries already access native
PostgreSQL tables, so an ordinary loadable module is the smaller interface.
This does not bypass PostgreSQL's planner, executor, MVCC, permissions, or WAL.

## Build and install

Linux x86-64, PostgreSQL 18 server headers/PGXS, GCC with LTO, binutils, make,
git, and Python 3 are required. Use the `pg_config` belonging to the server.
The fixed challenge tables must exist in `public`, in a UTF8 database.

```sh
cd experiments/nelua-postgres
PG_CONFIG=/path/to/postgresql18/bin/pg_config bash build.sh
make PG_CONFIG=/path/to/postgresql18/bin/pg_config install-strip
psql "$DATABASE_URL" -c 'CREATE EXTENSION nelua_conduit'
```

`make install-strip` removes unused binary symbols and needs permission to write that PostgreSQL installation's library
and extension directories; `CREATE EXTENSION` needs a PostgreSQL administrator.
Installation creates these functions, and does not change the challenge tables.
The project uses the repository's MIT license.

`build.sh` fetches the pinned fork and rejects a different or modified checkout.
To reuse an existing clean checkout, set `NELUA_ROOT=/path/to/nelua-lang`.
For a binary that will run only on the build machine, opt into CPU-specific
code generation with `NATIVE_FLAGS=-march=native bash build.sh` after `make clean`.
The default stays portable across x86-64 CPUs.

```sql
SELECT nc_tags();
SELECT nc_profile('alice', 42);
SELECT nc_article('hello-world-123', 42);
SELECT nc_articles(viewer => 42, page_limit => 10, tag => 'postgres');
SELECT nc_feed(42, 10, 0);
SELECT nc_comments('hello-world-123', 42);
SELECT nc_favorite('hello-world-123', 42, true);
SELECT nc_follow('alice', 42, false);
```

## SQL contract

All eight functions return the spec's JSON envelope, as PostgreSQL `json`.
JSON is already serialized; no extra JSON parse/rebuild occurs on return.

| Function | Arguments | Result |
| --- | --- | --- |
| `nc_tags` | none | `tags` array, sorted by name |
| `nc_profile` | username, viewer=0 | `profile` |
| `nc_article` | slug, viewer=0 | full `article` |
| `nc_articles` | viewer=0, page_limit=20, page_offset=0, tag=NULL, author=NULL, favorited=NULL | `articles` without body, `articlesCount` |
| `nc_feed` | viewer, page_limit=20, page_offset=0 | same page envelope for followed authors |
| `nc_comments` | slug, viewer=0 | newest 100 `comments` |
| `nc_favorite` | slug, viewer, active | full `article` after insertion/deletion |
| `nc_follow` | username, viewer, active | `profile` after insertion/deletion |

Unknown single resources return SQL NULL, including an unknown article's comment
collection; unknown list filters return an empty page. Pagination is 1–100 with
nonnegative int32 offset. Counts stop at 1,000. Filter precedence is tag, author,
then favorited; NULL means absent, while an empty string is an explicit filter.
Invalid pagination/viewer values raise SQLSTATE `22023`.

`viewer=0` means anonymous for reads. Feed and writes require a positive viewer.
The caller must authenticate that viewer: these functions do not verify JWTs or
passwords. They are SECURITY INVOKER and retain the caller's table privileges;
supplying a viewer is not an authentication mechanism. NULL required arguments
short-circuit to SQL NULL, except `nc_articles` rejects NULL viewer/pagination.

Writes participate in the caller's transaction. They **do not commit** when
returning a JSON value. An HTTP adapter must await successful COMMIT before
sending a successful write response. Read functions are STABLE/PARALLEL
RESTRICTED; write functions are VOLATILE/PARALLEL UNSAFE. Article/user/comment
creation, editing, deletion, login, registration, and HTTP transport remain
outside this module's current eight-function interface.

## Tuning that is actually implemented

Prepared SPI plans are retained per backend and invalidated by PostgreSQL as
needed. There is no `SPI_getvalue` conversion through textual SQL values:
rows are deformed once into binary Datums, text is detoasted lazily, and tags
are streamed from native arrays. IDs, counts, and flags stay binary until JSON
emission. Timestamps use UTC, exactly three fractional digits, and truncation
independent of the session's TimeZone or DateStyle.

Each article list first materializes a bounded ID page, then enriches only
that page with tags, counts, favorites, and author information. The feed merges
bounded per-followee ID streams before enrichment. A separate count stops after
1,000 source rows, matching the reference's page-then-count behavior.

The kernel copies ordinary string spans in blocks and escapes only the special
bytes. It uses scalar/stack storage and explicitly initialized local buffers.
All allocation and errors belong to PostgreSQL. The final response is copied
into the upper executor context before `SPI_finish` releases temporary memory.

O3, LTO, hidden helper symbols, section garbage collection, and inline append
paths optimize across the Nelua/C boundary. PostgreSQL's normal protection flags
remain enabled. `make audit` checks imports, exports, dependencies, generated
runtime paths, and constructor sections so added language weight fails the build.

## Verify and measure

```sh
make kernel-test
make audit
# The module must already be installed; PG* variables select a test server.
bash tests/run.sh
# Also run the optional page microbenchmark in that disposable fixture DB:
bash tests/run.sh --benchmark
```

The runner creates/drops its own `nc_test_*` database. The integration fixture
refuses to reset a database without that prefix. Tests compare decoded output
with independent SQL JSON oracles and cover filtering, caps, ordering, large
offsets, Unicode/control bytes, toasted text, timestamps, injection inputs,
plan reuse, rollback, concurrent writes, and caller permissions. Kernel tests
include 10,000 randomized int64 values and ASan/UBSan.

To measure an existing, unmodified seed database, run:

```sh
DATABASE_URL='postgresql://…/conduit' python3 tools/benchmark.py \
  --seconds 10 --clients 8 --threads 8 --rounds 3
```

The benchmark checks JSON parity first, then alternates prepared pgbench calls
against equivalent page-first SQL using `json_build_object`/`json_agg`. It writes
a Markdown report under `results/`. It does not run HTTP/auth, the full workload,
or establish a challenge ranking. See [VALIDATION.md](VALIDATION.md) for the
recorded development checks and their environment limitations.

A challenge-eligible server can reuse the Nelua serialization approach in a
standalone process with libpq, without installing this extension. That requires
implementing the remaining API and running the complete HTTP conformance suite.

## PostgreSQL references

- [C-compatible functions and module ABI](https://www.postgresql.org/docs/18/xfunc-c.html)
- [Server Programming Interface](https://www.postgresql.org/docs/18/spi.html)
- [SPI memory contexts and returned values](https://www.postgresql.org/docs/18/spi-memory.html)
- [Retained plans](https://www.postgresql.org/docs/18/spi-spi-keepplan.html)
- [Transaction management](https://www.postgresql.org/docs/18/spi-transaction.html)
