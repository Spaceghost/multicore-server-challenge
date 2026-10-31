# Feed hubs: exact shared count proofs and page floors

Scratch SQL prototype against the fixed full challenge seed. No application
source, database schema, or row data was changed. All derived values exist only
within one statement servicing the already-waiting requests.

## Approach and correctness

The input and output interface matches the existing feed statement: four text
array parameters (keys, viewers, limits, offsets); identical binary columns and
request ordinals. The candidate materializes each distinct viewer's followees
once, then considers at most 32 authors followed by multiple viewers in this
batch. A viewer with multiple page requests contributes its maximum page depth.

For a hub, let H be the maximum requested depth (`limit+offset`, overflow-clamped
as in the baseline) among viewers following it. If that author's H-th newest
article exists, its ID is a valid lower bound for every one of those viewers:
the viewer already follows at least its own requested depth of articles at or
above that ID from this author alone. Taking the maximum valid floor among a
viewer's followed hubs therefore cannot exclude any article its page needs.
All other followed-author index walks use that floor.

Separately, if a followed hub is proven to have at least 1,000 articles using
`EXISTS(... LIMIT 1 OFFSET 999)`, the viewer's capped feed count is exactly
1,000. The prototype bounds these proof attempts to
`min(16, number_of_distinct_viewers/2)` and prefers recent valid hub floors.
The cap changes proof cost, never the answer: without a successful proof the
original capped count is evaluated over the actual followee array.

Fallbacks are explicit. Empty followee sets count zero. Missing hub floors use
the minimum int64 ID, excluding nothing, including negative IDs. A hub with too
few articles for a requested deep page supplies no floor. Large offsets and
`INT64_MAX` offsets preserve the baseline's overflow-safe depth clamp. This
statement never interprets the count cap as a pagination bound.

The page ID list is put into a bounded ARRAY and unnested. This preserves the
baseline's useful generic-plan estimate (10 rows); without that boundary, the
additional floor selectivity estimated one page row and caused quadratic nested
joins over materialized pages/articles. The final measured candidate uses the
array boundary and retains hash joins.

This borrows the shared-hub proof/floor idea from the frozen top-five leader:
https://github.com/arjaythedev/multicore-server-challenge/blob/main/submissions/rust-epoll-theCatWisel/src/queries.rs

## Evidence and limits

Ten exact binary-row comparisons passed on `conduit_seed`: one/eight/32/128
viewers, empty and mixed-empty feeds, varying page depths, repeated viewers with
different pages, offset100000000, `INT64_MAX`, and a randomized128 request case.
The baseline and candidates were compared inside one repeatable-read snapshot.

The first candidate (without the array boundary) was rejected: it reduced index
work but caused up to 6.6 million discarded nested-loop join pairs. The saved
final plans show the corrected shape.

Short warmed comparative runs were performed only after the shared CPU benchmark
window was granted and other compiler/test workers were quiescent. The order was
baseline/full/floor-only/floor-only/full/baseline, one second each. These are
single-client SQL microbenchmarks, not HTTP results or official scores.

| Feed batch | Existing batches/s | Full candidate | Difference | Floor-only difference |
| --- | ---: | ---: | ---: | ---: |
| Eight viewers | 294.52 | 305.40 | +3.70%, noisy | +4.55% |
| 32 viewers | 80.30 | 98.85 | +23.11% | +14.62% |
| 128 viewers | 22.08 | 31.99 | +44.89% | +8.26% |
| 32 viewers, varying limits/offsets | 80.32 | 105.54 | +31.40% | +23.15% |

For the 128-viewer query, final EXPLAIN reduced shared-buffer hits from
29,833 to23,093 and approximately returned article-index rows from140,076 to37,590.
The estimate aggregates per-node rows times loops; EXPLAIN's average-row rounding
makes it approximate. Low-load/single-viewer behavior was also inspected, but
the short timing evidence is strongest for batches of32 or more.

No application promotion decision should rely solely on these numbers. Run
isolated full HTTP diagnostics with the normal mix, cold/warm conformance, and
overload recovery before changing the competition entry.

## Files

- `baseline.sql`: actual generated current feed SQL.
- `candidate.sql`: final full hub count/floor candidate (68 SQL lines).
- `floor-only.sql`: count-proof-disabled ablation.
- `generate.py`: extracts the generated baseline and builds these SQL variants.
- `prototype.py`: exact binary parity, complete EXPLAIN capture, comparative driver.
- `inputs.json`: every exact PostgreSQL array parameter used in the cases.
- `results.log`: raw parity, EXPLAIN summaries, and comparative timings.
- `validation.log`: separate earlier correctness/plan pass.
- `*-plan.json`: complete raw before/after EXPLAIN ANALYZE plans, including buffers.

The current scratch drivers expect the surrounding workspace's `pg18` libpq and
challenge checkout; they do not start PostgreSQL themselves. `DATABASE_URL`
selects a full-seed database. Python uses only its standard library plus libpq.
Use `prototype.py` without `--benchmark` for correctness/plans. Sustained timings
require a separately coordinated CPU window. No generated binaries are needed.
