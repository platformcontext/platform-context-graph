# Facts Package

Typed fact models, Postgres-backed fact storage, queue state, and fact emission
helpers live here.

This package now owns the source-of-truth ingestion layer for the Git facts-first
pipeline:

- `models/` defines typed repository, file, and parsed-entity observation facts
- `storage/` persists fact runs and fact records in Postgres
- `work_queue/` coordinates downstream projection work in Postgres
- `emission/` turns parsed repository snapshots into durable facts
- `state.py` owns shared fact store / queue lifecycle for deployed runtimes

Current Git flow:

1. the Git collector parses a repository snapshot
2. `facts/emission/git_snapshot.py` persists repository, file, and entity facts
3. one queued work item is created for that repository snapshot
4. during the current cutover, the indexing coordinator can lease that queued
   work item inline and project canonical graph state through `resolution/`
5. the standalone `resolution-engine` runtime can claim the same queue for
   background processing and future multi-collector flows

This package should continue to grow as new collectors emit source observations
before graph projection.
