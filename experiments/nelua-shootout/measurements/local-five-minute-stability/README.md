# Five-minute full-seed stability hold

Candidate 2a07dab, default 128-request batches, serialized gathering and read pipelining enabled; 20 database connections. Fresh full-seed clone, 10-second warm-up, 5-second ramp, 300-second measurement, 3-second tail. The 8,000 users use think scale 0.1. The generator models equilibrium session starts from the beginning; the long hold checks sustained behavior across multiple session rotations.

- 5,633,747 measured requests; **18,779.16 req/s**.
- p95 **122.879ms**, p99 **213.503ms**.
- **5,070 HTTP 503 errors (0.0900%)**, included in the official loadgen totals. Transport backpressure applies across route families; failures are not hidden or excluded.
- Workload SLO **pass**, load-generator limited **no**; host CPU **71.20%**, database connection peak **20**.

There were 6,638 login and 136 signup session starts. The request queues and 128 MiB pending-byte limit remain bounded, cost 10 bcrypt and per-request JWT verification stay active, and writes commit before responses. No process restart occurred. The local PID/procfs mismatch means application RSS/CPU are unavailable; host/loadgen CPU remains recorded. The raw file's rss_peak_mb is the load generator's RSS.

This is a local accelerated stability diagnostic, not an official score or top-five capacity comparison. The shared-host/memory/descriptor/PostgreSQL differences are captured in environment.tsv. Complete raw loadgen data, statuses, logs, executable hash, sampled connections and batch statistics are retained.
