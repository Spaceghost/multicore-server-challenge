# Nelua versus the frozen top five

This research workflow compares `nelua-epoll-spaceghost` only with the five entries in
[pins.tsv](pins.tsv). Their rank, source commit, source tree, and toolchain are frozen.
Comparator sources must match those pins; a blocked entry stays in the report and is
never replaced by a lower-ranked implementation. Nothing here belongs in the contest entry.

The workflow builds and starts the original submissions without source patches.
Readiness uses a standard persistent HTTP/1.1 request, matching the official curl/Go
clients, and drains its response before closing the connection.

Run `build-all.sh LOG_DIRECTORY` on a disposable Ubuntu 24.04 host to install their toolchains
and build all six, preserving each install/build log. It continues through individual
failures. `SHOOTOUT_SKIP_INSTALL=1` skips dependency installation on a prepared host.
Only the original dependency installers run with `sudo`; benchmark servers run as the
invoking user. The harness changes no sysctl, affinity, NIC, compiler, or global PostgreSQL
setting. It lowers each server child's descriptor limit to 200000, or the available hard
limit if lower, and records that deviation.

`ci-workflow.yml` is a template for `.github/workflows/nelua-top5-shootout.yml`. Pushes run
a short diagnostic against the full verified seed. Manual dispatch selects load points,
repetitions, real or accelerated think time, and bounded 300-second holds. All six cases
run sequentially on the same Ubuntu 24.04 runner with PostgreSQL 18. The full seed,
compiler/build logs, conformance, and results are uploaded even when coverage fails.
The stock CI database configuration is recorded as a diagnostic environment; it is not
represented as the contest's dedicated eight-core machine.

The first two research CI runs built all six unchanged entries, but the original
urllib readiness probe added `Connection: close`, which triggered C#'s premature
asynchronous response close path. Those reports correctly show incomplete coverage;
their five measured cases remain diagnostics. The harness now matches the official
persistent HTTP client behavior for every entry. No comparator source was changed.

For an existing PostgreSQL 18 instance, first build `bench/cmd/conformance` and
`bench/cmd/loadgen`, and run the repository's `seed/make-seed.sh` normally. Supply the
usual `PGHOST`, `PGPORT`, `PGUSER`, and `PGPASSWORD` variables for a role allowed to clone
the seed database. The application always connects as the seed's `conduit` role. Example:

```sh
python3 experiments/nelua-shootout/shootout.py \
  --conformance /absolute/path/to/conformance --loadgen /absolute/path/to/loadgen \
  --template conduit_seed --articles 500000 \
  --users 2000,5000,10000 --think-scale 1 --measure 20 --rounds 1 \
  --output /absolute/path/to/new-empty-results
```

Every conformance invocation and every measured case receives a fresh database cloned
from the same pristine template. Warm-up precedes measurement within that fresh case.
Only the harness's own `nc_shoot_*` databases are dropped. Six rounds form a seeded,
Williams-balanced order block covering every position and directed predecessor pair;
shorter runs are labeled partial blocks. All competitors receive the same load points,
think scale, durations, and seed data. Use `--think-scale 0.1` only for explicitly
accelerated diagnostics: those virtual users are not equivalent to official users.

For prepared local binaries, `--cases cases.tsv` accepts actual tab-separated columns
`name`, `launcher` (or `binary`), and optional `cwd`/`sourcepin`. A supplied comparator
source pin must match its frozen commit or directory tree. Exactly the six names are required.
An optional Nelua pin must match the clean current commit/tree; omit it for a dirty
candidate experiment, whose actual tracked source hash and dirty flag are still recorded.
Launchers may be original start scripts or prebuilt executables. Their paths and the
running executable hash are captured. Missing binaries, denied `io_uring_setup`, and
build/start/conformance failures stay visible as blocked or failed cases. This is useful
in sandboxed hosts that cannot run the pinned Zig or Native AOT implementations.

Native-only transport ablations use repeated options, for example:

```sh
--nelua-variant baseline:READ_GATHER_SERIAL=0,READ_PIPELINE=0 \
--nelua-variant candidate:READ_GATHER_SERIAL=1,READ_PIPELINE=1
```

Only documented numeric Nelua knobs are accepted. Other implementations keep their
original runtime configuration. Each variant passes its own conformance; variant order
reverses on even rounds. Enable a knob only when the tested candidate implements it.

`SUMMARY.md` presents per-load medians. `runs.tsv` preserves every result, including
latencies, errors, load-generator limitation flags, host/load-generator CPU, application
RSS, and sampled PostgreSQL connections. Raw official load-generator JSON and logs,
source hashes, launchers, runtime settings, capabilities, and one-second process samples
are kept alongside it. Connection counts above 95 fail a run; these are observed sample
peaks, not a proof that shorter spikes cannot occur. RSS sums process RSS and may count
shared mappings more than once. Process CPU jiffies are available in the raw samples.
If process inspection is unavailable, or `/proc` exposes a different PID namespace
from the harness, app CPU/RSS cells are blank/unavailable. Host CPU is not substituted.

Exit status 0 means every requested case and variant passed conformance, thresholds,
connection sampling, and load-generator eligibility. Status 2 means partial or ineligible
coverage; status 1 is a harness/setup error. No short same-host run declares an official
capacity winner. A real contest ceiling requires the maintainer's isolated hardware,
separate unsaturated clients, the unscaled workload, and the full prescribed hold.

The host-independent tests exercise the exact allowlist, source manifest, balanced
ordering, descriptor limits, native variants, and fake blocked/load-generator-limited
matrix orchestration:

```sh
python3 -m unittest discover -s experiments/nelua-shootout/tests -v
```
