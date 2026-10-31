# Rejected unified-page prototype

**Keep this outside the submission.** Combining all five page families passed exact binary-row parity, including unknown filters, empty feeds, 128-request batches and large offsets. It improved ordinary mixed batches only about 3%, for 82 lines of extra SQL plus dispatcher changes. The existing implementation remains in the PR.

| Batch | Existing batches/s | Unified batches/s | Change |
| --- | ---: | ---: | ---: |
| Mixed 32 |106.44 |109.89 |+3.24% |
| Mixed 128 |35.33 |36.60 |+3.61% |
| Highly shared 128 |139.93 |162.20 |+15.92% |

The baseline already pipelines the five family queries behind one Sync, avoiding an unfair five-round-trip comparison. Four alternating one-second runs use the full seed and production session settings. These are short SQL microbenchmarks, not application scores. EXPLAIN found article enrichment only 154→151 and 457→448 rows on mixed batches; shared-buffer hits fell 5,945→5,890 and 20,519→19,212. The special highly shared case overstates the benefit for normal diverse requests.

Fixed SQL, complete timing/parity output and EXPLAIN summaries are retained. On an immutable full Conduit seed, set DATABASE_URL and optionally LIBPQ, then run `python3 compare.py --benchmark --explain --seconds 1`. The script uses session settings and SELECTs; it changes no data. Its stored baseline statements were emitted from candidate 2a07dab. Machine/database limitations match the other local ablations.

The SQL baseline and candidate use identical parameter vectors; no load-generator RNG is involved.
