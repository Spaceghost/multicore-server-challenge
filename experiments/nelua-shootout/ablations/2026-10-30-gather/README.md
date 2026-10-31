# Serial read collection ablation

Full `conduit_seed` (500,000 articles), PostgreSQL18, fresh clone per run, local load generator. One binary built from published784535 plus only the serialized-collection patch; compiler remains pinned3c294197. Four runs in0/1/1/0 order,5,000 virtual users, accelerated think scale0.1,5-second ramp,20-second measurement,3-second tail. Four read workers; other pools remain8/8. `READ_BATCH_STATS=1`.

This is a development ablation, not an official score or a top-five ranking. All runs have zero errors and are not load-generator limited. Stock local PostgreSQL shared_buffers128MiB/max_connections100;9 visible CPUs; descriptor hard limit 16,384. The local PostgreSQL root-start guard is disabled only in the scratch test build; query/executor/MVCC code is unchanged.

| Collection | Median req/s | Medianp95 ms | Median host CPU | Mean batch size |
| --- | ---: | ---: | ---: | ---: |
| Independent collectors |12,106.7 |51.551 |47.30% |104.73 / 103.98 |
| Single collector, concurrent execution |12,211.5 |44.335 |44.90% |123.96 /123.88 |

At this load, median p95 fell 14.0%, throughput rose 0.87%, and hostCPU fell 2.4 percentage points. p99 varies between repeats; no p99 improvement is claimed. Results are evidence to investigate larger batches, not a capacity result. JSON files retain complete official loadgen aggregates; server logs retain density and queue-wait statistics.
