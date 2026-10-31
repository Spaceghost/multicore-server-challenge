# Optional selected-build stability hold: blocked before startup

The optional validation hold was not run. This sandbox maps only UID/GID 0
(`0 0 1`); it cannot represent an ordinary application user. Switching to UID
65534 with `setpriv` fails with `Invalid argument`; `runuser nobody` fails with
`cannot set groups: Operation not permitted`. All capability sets are zero and
`NoNewPrivs` is 1. No mappings, capabilities, host settings, or privileges were
changed to work around this restriction.

The preflight verified clean application commit
`bc35c96ef444521151f6f3a78591f39b59f21b6e`, compiler pin
`4b5dfd4a76ce4f6e3c59983295f32f7db68466b4`, and executable SHA-256
`8e7ea48034baa456bcb68b49a78b2bbe84a57be295317a41f17802313d46d101`.

PostgreSQL, the application, and the load generator were never started. There
are no measured requests, CPU/latency/error/connection/RSS results, merged
load-generator JSON, or eligible stability score from this attempt. The runtime
PID/procfs mismatch would also make application RSS/CPU unavailable locally.

`identity-preflight.json`, `uid-map.txt`, `gid-map.txt`, `capabilities.txt`,
`metadata.json`, and `result.json` retain the actual preflight evidence. The
guarded reusable driver is recorded in the research repository as
`experiments/nelua-shootout/measurements/catchup-v2/stability-driver.py`.
