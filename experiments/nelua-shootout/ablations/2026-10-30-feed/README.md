# Feed follow-flag ablation

The feed join already proves that the requesting viewer follows the article author. Replacing the redundant follows lookup with `a.id IS NOT NULL` preserves true for real articles and false on the empty-page marker. Both fixed statements are retained here.

Six exact binary-row parity cases passed against the full 500,000-article seed in one repeatable-read snapshot, including an empty viewer, mixed empty/real viewers, limits 1/100, and offsets 20/10,000. Four alternating one-second timing runs used the production session settings.

| Batch | Original queries/s | Candidate queries/s | Change |
| --- | ---: | ---: | ---: |
|32 distinct viewers |89.72 |91.95 |+2.49% |
|128 requests, 32 distinct viewers |64.21 |71.32 |+11.07% |

These short SQL microbenchmarks are development evidence, not an application score. The PostgreSQL/local-machine limitations are the same as the adjacent gather and pipeline ablations. `results.log` contains each sample and parity result.

To repeat on an immutable Conduit seed, set `DATABASE_URL` and run `python3 compare.py --benchmark --seconds 1`. Use `--seconds 1` with a separating space; optional `LIBPQ` selects the libpq shared library. The script uses only session settings and SELECTs.

The SQL baseline and candidate use identical parameter vectors; no load-generator RNG is involved.
