# Baseline Performance: Neo4j + Postgres (v0.0.42)

Date: 2026-04-04 (Run #5 -- first complete 896-repo run)
Configuration: CW=2, facts-first mode, 896 repos (24 GB source), Docker Compose on 123 GiB RAM instance

## Executive Summary

Full 896-repo e2e benchmark using Neo4j + Postgres as the backing stores.
This is the **first complete run** in project history -- previous runs stalled
(Run #1), OOM'd (Run #2), or were interrupted (Runs #3/#4). It serves as the
comparison baseline for the planned ArcadeDB evaluation.

**Key findings:**

- All **896 repos** indexed in **~3 hours 37 minutes** (parse + commit + projection)
- **8,994,038 facts** stored in Postgres (21 GB total database)
- **1,445,012 nodes** and **31,072,991 relationships** in Neo4j
- **154,636 files** parsed across all repos
- **Zero OOM events** despite five repos with 7K--12K files each
- **Zero fatal errors** -- 6 transient Neo4j deadlocks, all auto-recovered
- Peak memory: 19.87 GiB (spike during large repo parse, released after)
- Partitioned streaming projection validated: memory proportional to batch
  size (~2K rows), not total repo size

## Test Environment

| Component | Details |
|---|---|
| Instance | 123.1 GiB RAM, multi-core |
| Storage | 484 GB root volume (ext4) |
| Postgres | Default Docker image, tuned config (see Tuning section) |
| Neo4j | Community edition, Docker |
| Source data | 896 repos, 24 GB on disk |
| PCG version | 0.0.42 |
| Commit workers | 2 (`PCG_COMMIT_WORKERS=2`) |
| Parse strategy | threaded, 4 workers |
| Mode | facts-first (inline projection) |
| pcgignore | Helm default patterns (vendor/, node_modules/, dist/, etc.) |
| Fact upsert batch | 2,000 rows (`PCG_FACT_UPSERT_BATCH_SIZE`) |

## Timeline

| T+ | Event |
|---|---|
| 0min | `docker compose up --build`, bootstrap lock acquired |
| 7min | All 896 repos discovered |
| 10min | First 70 repos parsed, 50K facts |
| 15min | 108 parsed, PHP monster parse complete (237s) |
| 37min | PHP monster commit complete (1,203s / 20 min) |
| 80min | 620 parsed (69%), steady 5 repos/min |
| 107min | search-api-legacy (12K files) parsing, bootstrap spike 19.87 GiB |
| 117min | search-api-legacy done, resolution spike 11.57 GiB, then released |
| 137min | 733 parsed (82%), rate 5 repos/min, all memory at baseline |
| 157min | 839 parsed (94%), Neo4j crossed 1M nodes |
| 172min | websites-php-youboat (12,747 files) parsing -- largest repo |
| 182min | wordpress (8,431 files) parsing |
| 192min | 895 parsed, big commits draining |
| 212min | wordpress commit done (1,349s). youboat last commit running |
| **217min** | **896/896 complete. youboat commit: 2,070s (34.5 min)** |

## Repo Size Distribution

| Size Bucket | Repos | Avg Files | Total Files | % of Corpus |
|---|---|---|---|---|
| Tiny (1--10 files) | 302 | 4 | 1,153 | 0.7% |
| Small (11--50) | 353 | 24 | 8,415 | 5.4% |
| Medium (51--200) | 129 | 95 | 12,236 | 7.9% |
| Large (201--1,000) | 80 | 487 | 38,935 | 25.2% |
| XL (1,001--5,000) | 27 | 1,537 | 41,512 | 26.8% |
| Monster (5,000+) | 5 | 10,477 | 52,385 | 33.9% |
| **Total** | **896** | **173** | **154,636** | **100%** |

The 5 monster repos (0.6% of repos) contain 34% of all files and dominate
total runtime.

## Parse Performance

| Statistic | Value |
|---|---|
| Total duration (sum) | 5,730s |
| Mean | 6.4s |
| Median | 0.3s |
| P90 | 6.3s |
| P95 | 17.4s |
| P99 | 188.8s |
| Max | 479.8s (wordpress) |

### Slowest Parses

| Repo | Files | Parse Time | Rate (f/s) |
|---|---|---|---|
| wordpress | 8,431 | 479.8s | 17.6 |
| websites-php-youboat | 12,747 | 408.7s | 31.2 |
| boattrader-legacy | 12,124 | 450.9s | 26.9 |
| portal-java-ycm | -- | 334.0s | -- |
| portal-nextjs-platform | -- | 281.9s | -- |
| search-api-legacy | 12,014 | 253.2s | 47.4 |
| api-php-boatwizardwebsolutions | 7,069 | 236.9s | 29.8 |
| portal-react-platform | -- | 211.1s | -- |

PHP files parse faster per-file (30+ f/s) than Node.js/Java repos (10--20 f/s)
because PHP ASTs are structurally simpler.

## Commit Performance

| Statistic | Value |
|---|---|
| Total duration (sum) | 24,683s |
| Mean | 27.5s |
| Median | 3.5s |
| P90 | 33.0s |
| P95 | 68.5s |
| P99 | 363.8s |
| Max | 2,564.7s (boattrader-legacy) |

### Slowest Commits (Top 10)

| Repo | Files | Commit Time | Notes |
|---|---|---|---|
| boattrader-legacy | 12,124 | 2,565s (43 min) | Largest commit |
| search-api-legacy | 12,014 | 2,241s (37 min) | |
| websites-php-youboat | 12,747 | 2,070s (34.5 min) | Most files |
| portal-java-ycm | -- | 1,594s (26.6 min) | Java monorepo |
| wordpress | 8,431 | 1,349s (22.5 min) | |
| api-php-boatwizardwebsolutions | 7,069 | 1,203s (20 min) | PHP monster |
| webapp-grails-imt | -- | 1,066s (17.8 min) | Grails monorepo |
| portal-boattrader-zf1 | -- | 785s (13 min) | |
| marketing.boatsgroupwebsites.com | -- | 377s (6.3 min) | |
| webapp-react-leadsmart | -- | 364s (6.1 min) | |

Commit includes: graph writes, content store, fact emission, inline
projection, and workload materialization. Large repos dominate because
graph writes scale with entity count.

## Memory Profile

### Peak Memory by Phase

| Container | Peak | During | Baseline |
|---|---|---|---|
| bootstrap-index | **19.87 GiB** | search-api-legacy parse | 4.2 GiB |
| resolution-engine | **12.0 GiB** | search-api-legacy projection | 0.8 GiB |
| postgres | 5.16 GiB | Steady during writes | 4.9 GiB |
| neo4j | 4.4 GiB | Graph write burst | 2.8 GiB |

### Spike-and-Release Pattern (validated)

Large repos cause temporary memory spikes that reliably drop back to
baseline after processing completes:

| Repo | Peak Bootstrap | After Release | Peak Resolution | After Release |
|---|---|---|---|---|
| PHP monster (7K files) | 16 GiB | 4.4 GiB | -- | -- |
| search-api-legacy (12K) | 19.87 GiB | 4.3 GiB | 11.57 GiB | 1.2 GiB |
| websites-php-youboat (12.7K) | 15.23 GiB | 4.5 GiB | 12.0 GiB | 1.8 GiB |
| wordpress (8.4K) | -- | -- | 12.0 GiB | 1.8 GiB |

The streaming projection keeps peak memory proportional to one batch
(~2,000 rows / ~1 MB), not the total fact count. Without this fix,
Run #2 OOM'd at 98 GiB on a 216K-fact repo.

## Storage Profile

### Postgres Table Sizes (final)

| Table | Size | Notes |
|---|---|---|
| content_entities | 11 GB | Parsed entities (functions, classes, etc.) |
| fact_records | 8.6 GB | 8,994,038 rows; TOAST dominated |
| content_files | 936 MB | File content store |
| projection_decision_evidence | 13 MB | |
| projection_decisions | 3.2 MB | |
| runtime_repository_coverage | 704 KB | All 896 repos tracked |
| fact_work_items | 520 KB | |
| **Total database** | **21 GB** | |

### Storage Ratios

| Metric | Value |
|---|---|
| Source data | 24 GB (896 repos on disk) |
| Postgres total | 21 GB |
| Source-to-DB ratio | 0.88:1 (DB smaller than source) |
| Avg fact record size | ~980 bytes |
| Avg content entity size | ~90 bytes |

## Neo4j Graph Profile

### Node Distribution (1,445,012 total)

| Label | Count | % |
|---|---|---|
| Function | 751,564 | 52.0% |
| Parameter | 250,367 | 17.3% |
| File | 154,588 | 10.7% |
| TerraformVariable | 69,266 | 4.8% |
| Class | 47,457 | 3.3% |
| TerraformResource | 37,173 | 2.6% |
| TerraformLocal | 33,353 | 2.3% |
| Module | 31,913 | 2.2% |
| TerraformDataSource | 19,050 | 1.3% |
| Directory | 15,087 | 1.0% |
| TerraformOutput | 14,155 | 1.0% |
| TerraformModule | 6,230 | 0.4% |
| Interface | 5,555 | 0.4% |
| TerraformProvider | 5,515 | 0.4% |
| Repository | 896 | 0.1% |

### Relationship Distribution (31,072,991 total)

| Type | Count | % |
|---|---|---|
| CALLS | 28,862,735 | 92.9% |
| CONTAINS | 1,471,077 | 4.7% |
| HAS_PARAMETER | 383,699 | 1.2% |
| IMPORTS | 198,890 | 0.6% |
| REPO_CONTAINS | 154,588 | 0.5% |
| INHERITS | 1,002 | <0.1% |
| DEFINES | 896 | <0.1% |
| DEPENDS_ON | 62 | <0.1% |
| PROVISIONS_PLATFORM | 42 | <0.1% |

**Density:** 21.5 relationships per node (dominated by CALLS edges from
PHP/JS function resolution).

## Resolution Engine Metrics

| Metric | Value |
|---|---|
| Inline projections (bootstrap) | 896 |
| Resolution engine re-projections | 20 |
| Total work items projected | 916 |
| Transient Neo4j deadlocks | 6 (all auto-recovered) |
| Fatal projection errors | 0 |

## Error Summary

| Error Type | Count | Impact |
|---|---|---|
| Neo4j TransientError.DeadlockDetected | 6 | Auto-recovered, zero data loss |
| Fatal errors | 0 | -- |
| OOM events | 0 | -- |
| Application exceptions | 0 | -- |

All 6 deadlocks occurred in `call_batches.py` during concurrent call
resolution (bootstrap + resolution engine writing to overlapping nodes).
The retry logic in the driver handled all cases transparently.

## Run Comparison

| | Run #1 | Run #2 | Run #5 |
|---|---|---|---|
| Date | Apr 3 | Apr 3 | **Apr 4** |
| Config | Vanilla | + chunked INSERT | **+ streaming + keyset** |
| Repos completed | 132 (15%) | ~132 (OOM) | **896 (100%)** |
| Outcome | Stalled | OOM killed | **Complete** |
| Wall clock | 142min (stopped) | ~45min (crashed) | **217min (done)** |
| Facts | 132,399 | ~216K then OOM | **8,994,038** |
| DB size | 68 GB (stalled) | unknown | **21 GB** |
| Neo4j nodes | 51,039 | -- | **1,445,012** |
| Neo4j rels | 120,603 | -- | **31,072,991** |
| OOM events | 0 | 1 | **0** |
| Peak memory | 11.5 GiB | 98 GiB (OOM) | **19.87 GiB** |

### PHP Monster Comparison

| | Run #1 | Run #5 |
|---|---|---|
| Files indexed | 7,240 | 7,069 (pcgignore=171) |
| Parse time | 361s | 237s |
| Commit time | 2h+ (never finished) | **1,203s (20 min)** |
| Pipeline stall | YES (2+ hours) | **NO** |
| DB impact | 68 GB (single txn) | ~4 GB (chunked) |

### What Changed Between Runs

1. **Chunked executemany** (Run #2+): 2,000-row batches instead of one
   mega-transaction. Prevents multi-hour TOAST writes.
2. **Partitioned streaming projection** (Run #3+): Load facts by type at
   SQL level. Entity facts streamed in 2,000-row batches via keyset
   pagination. Peak memory proportional to batch, not total repo.
3. **Entity keyset partial index** (Run #4+):
   `fact_records_entity_keyset_idx ON (repository_id, source_run_id, relative_path, fact_id) WHERE fact_type = 'ParsedEntityObserved'`
   gives O(log n) batch loading.
4. **pcgignore** (Run #3+): Excludes vendor/generated files at discovery
   time, reducing parse and fact volume.

## Postgres Tuning (Applied)

| Setting | Value | Justification |
|---|---|---|
| `shared_buffers` | 4 GB | 3% of 123 GiB; TOAST writes are sequential |
| `work_mem` | 16 MB | Simple queries, no complex JOINs |
| `maintenance_work_mem` | 512 MB | Fast DDL at startup |
| `max_wal_size` | 8 GB | Checkpoints every ~13 min at write rate |
| `wal_buffers` | 64 MB | Buffers ~6s of WAL |
| `effective_cache_size` | 32 GB | ~25% of RAM, planner hint |
| `synchronous_commit` | off | 2-3x bulk write throughput |
| `default_toast_compression` | lz4 | 3-5x faster than pglz |
| `effective_io_concurrency` | 200 | SSD optimization |
| `random_page_cost` | 1.1 | SSD tuning |

## Future Optimizations

1. **COPY instead of INSERT:** `psycopg3.copy` with binary mode for bulk
   fact loads. Expected 3-10x over `executemany`.
2. **JSONB compression:** Pre-compressed `bytea` with zstd instead of raw
   JSONB. 5-10x better ratios than TOAST.
3. **Expanded pcgignore:** Add patterns for `files/pls/` directories in
   legacy PHP repos to exclude bloated vendor trees.
4. **Neo4j deadlock mitigation:** Serialize call resolution per-repo or
   use advisory locks to prevent concurrent writes to shared nodes.

## Comparison Notes for ArcadeDB Evaluation

When comparing against ArcadeDB, use these as the baseline targets:

1. **Total throughput:** 896 repos in 217 min (~4.1 repos/min sustained)
2. **Parse throughput:** median 0.3s, mean 6.4s per repo
3. **Commit throughput:** median 3.5s, mean 27.5s per repo
4. **Monster repo commit:** 20-43 min for 7K-12K file repos
5. **Storage efficiency:** 21 GB for 8.9M facts + 154K files
6. **Graph size:** 1.4M nodes, 31M rels, density 21.5 rels/node
7. **Memory ceiling:** 19.87 GiB peak, returns to 4 GiB baseline
8. **Reliability:** Zero OOM, zero fatal errors, 6 transient deadlocks
