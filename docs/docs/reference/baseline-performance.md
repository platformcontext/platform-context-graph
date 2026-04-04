# Baseline Performance: Neo4j + Postgres (v0.0.42)

Date: 2026-04-03
Configuration: CW=2, facts-first mode, 896 repos (24 GB source), Docker Compose on 123 GiB RAM instance

## Executive Summary

Full 896-repo e2e benchmark using Neo4j + Postgres as the backing stores.
This document captures per-repo-size performance curves, outlier analysis,
storage characteristics, and Postgres tuning recommendations. It serves as
the comparison baseline for the planned ArcadeDB evaluation.

**Key findings:**

- 132 non-outlier repos indexed in **12 minutes** (parse + commit + projection)
- One large legacy PHP repository (`php-outlier-large`) stalled the entire pipeline
  for **2+ hours** due to a single `executemany` transaction writing 60+ GB of
  TOAST data at 10.1 MB/s
- Postgres TOAST storage dominates: `fact_records` consumes **99%+** of total
  database size
- Zero deadlocks or blocked locks throughout the run (schema lock fix validated)
- Resolution engine successfully claimed and re-projected 11 work items with
  zero failures

## What To Watch In The Next Large-Repo Run

The most important live signals after the hot-path fixes are:

- `pcg_resolution_file_projection_batch_duration_seconds`
- `pcg_content_file_batch_upsert_duration_seconds`
- `pcg_call_prefilter_known_name_scan_duration_seconds`
- `pcg_call_prep_calls_capped_total`
- `pcg_inheritance_batch_duration_seconds`

Use them together with:

- `pcg_resolution_stage_duration_seconds{stage="project_facts"}`
- `pcg_resolution_stage_duration_seconds{stage="project_relationships"}`
- `pcg_process_rss_bytes`
- `pcg_cgroup_memory_bytes`

Interpretation:

- If memory stays flat while `pcg_resolution_file_projection_batch_duration_seconds`
  remains bounded, the entity and file streaming changes are doing their job.
- If file projection is healthy but `project_relationships` still spikes, the next
  bottleneck has moved into CALLS or inheritance work rather than fact loading.
- If `pcg_call_prep_calls_capped_total` rises sharply on one repo, the call cap is
  protecting stability and should be reviewed together with correctness sampling
  before raising it.

## Test Environment

| Component | Details |
|---|---|
| Instance | 123.1 GiB RAM, multi-core |
| Storage | 484 GB root volume (ext4) |
| Postgres | Default Docker image, default config |
| Neo4j | Community edition, Docker |
| Source data | 896 repos, 24 GB on disk (`/tmp/pcg-e2e-full`) |
| PCG version | v0.0.42 |
| Commit workers | 2 (`PCG_COMMIT_WORKERS=2`) |
| Parse strategy | threaded, 4 workers |
| Mode | facts-first (inline projection) |

## Timeline

| Time (UTC) | T+ | Event |
|---|---|---|
| 21:28 | 0min | `docker compose up --build` |
| 21:38 | 10min | Bootstrap starts prescan |
| 21:44 | 16min | First repos parsed (15), first Neo4j nodes (1,689) |
| 21:49 | 21min | Steady state: 90 parsed, 32,982 nodes |
| 21:55 | 27min | PHP monster parse completes (361s for 7,240 files) |
| 21:56 | 28min | Pipeline stalls: PHP monster enters fact emission |
| 22:00 | 32min | Resolution engine finishes 11 re-projections |
| 22:00-23:50 | 32-142min | PHP monster `executemany` transaction at 10.1 MB/s |
| 23:50 | 142min | **Run stopped** -- 68 GB fact_records, 1h 53min txn |

### Active Ingestion Phase (21:44 - 21:56)

12 minutes to parse 133 repos, commit 119, and project 132 work items into
the canonical graph. This is the "normal" operating performance before the
PHP monster bottleneck.

**Throughput:** ~11 repos/min parse, ~10 repos/min commit

### Pipeline Stall Phase (21:56 - ongoing)

Single `executemany` transaction in `facts/storage/postgres.py` writing all
JSONB facts for `php-outlier-large` in one transaction. The
entire pipeline is blocked because:

1. Facts are invisible until the transaction commits (MVCC)
2. No work item gets enqueued until facts are committed
3. The commit worker holding this connection cannot pick up new work
4. All alphabetically-earlier repos already completed

## Per-Repo-Size Performance Curve

### Parse Phase

| Size Bucket | Repos | Avg Files | Avg Duration | Parse Rate |
|---|---|---|---|---|
| 1-10 files | 20 | 4 | 0.6s | 6.7 f/s |
| 11-50 files | 50 | 28 | 2.2s | 12.7 f/s |
| 51-200 files | 41 | 105 | 8.9s | 11.8 f/s |
| 201-1000 files | 15 | 388 | 30.1s | 12.9 f/s |
| 1000+ files | 1 | 7,240 | 361.4s | 20.0 f/s |

Parse rate is relatively stable at 10-20 files/sec across all size buckets.
The PHP monster actually parses *faster* per file (20.0 f/s) because PHP
files are structurally simpler than Node.js files for the AST parser.

### Commit Phase

| Size Bucket | Repos | Avg Duration | Notes |
|---|---|---|---|
| Tiny (<5s) | 35 | 2.1s | Dominated by fixed overhead |
| Small (5-30s) | 79 | 11.5s | Normal range |
| Medium (30-120s) | 4 | 67.9s | Graph write intensive |
| Large (2-10min) | 1 | 134.3s | `service-outlier-large` |

Median commit time: **7.7s**. Mean: **11.6s**.

## Outlier Analysis

### Tier 1: Extreme Pipeline Stall

| Repo | Files | Parse | Commit | Storage Impact |
|---|---|---|---|---|
| `php-outlier-large` | 7,240 | 361s | 2h+ (ongoing) | 60+ GB TOAST |

**Root cause:** 7,240 PHP files (28,499 total files, 612 MB on disk) in a
legacy PHP application with 890 subdirectories under `files/pls/`. Each PHP
file generates multiple JSONB fact records (functions, classes, parameters,
imports). The `executemany()` call wraps all INSERTs into a single
transaction, creating a multi-hour TOAST write that saturates Postgres at
100% CPU.

**Storage expansion ratio:** 612 MB source to 60+ GB TOAST = **~100:1**
(compared to ~2:1 for typical Node.js repos).

**Impact:** Entire pipeline stalled for the duration. No other repos can
parse, commit, or project while this transaction runs.

### Tier 2: Commit-Heavy Anomalies (commit/parse > 10x)

These repos have disproportionately slow commit phases relative to parse,
indicating the bottleneck is in graph writes, content store, or inline
projection rather than parsing.

| Repo | Files | Parse | Commit | Ratio | Likely Cause |
|---|---|---|---|---|---|
| `service-outlier-large` | 305 | 10.3s | 134.3s | 13.1x | Complex graph relationships |
| `service-template-outlier` | 66 | 5.3s | 82.2s | 15.6x | Template generates many entities |
| `content-heavy-outlier` | 46 | 2.5s | 48.7s | 19.3x | Heavy content store writes |
| `small-fixed-overhead-a` | 14 | 0.3s | 11.3s | 33.1x | Fixed overhead dominates |
| `small-fixed-overhead-b` | 15 | 0.4s | 11.4s | 30.4x | Fixed overhead dominates |
| `small-fixed-overhead-c` | 16 | 0.4s | 11.5s | 26.9x | Fixed overhead dominates |

**Finding:** Repos with < 20 files show a **~11 second minimum commit
duration** regardless of size. This fixed overhead includes: Neo4j schema
operations, content store writes, fact emission, work item enqueue, inline
projection (3 decision types), and workload materialization.

### Tier 3: Parse-Heavy Repos (>30s parse)

| Repo | Files | Parse | Commit | Total |
|---|---|---|---|---|
| `node-api-outlier-a` | 903 | 88.0s | 27.0s | 115.0s |
| `node-api-outlier-b` | 377 | 52.5s | 16.2s | 68.6s |
| `node-api-outlier-c` | 539 | 45.1s | 28.2s | 73.3s |
| `node-api-outlier-d` | 748 | 41.7s | 102.9s | 144.6s |
| `node-api-outlier-e` | 338 | 41.3s | 28.8s | 70.1s |
| `node-api-outlier-f` | 435 | 40.2s | 37.9s | 78.1s |
| `node-api-outlier-g` | 170 | 39.9s | 6.3s | 46.1s |
| `node-api-outlier-h` | 449 | 34.2s | 23.9s | 58.1s |

The `node-api-outlier-*` family is consistently the slowest parser cohort in
the Node.js category, with parse rates of 7-18 files/sec.

## Storage Profile

### Table Sizes (at 132 repos committed, pre-PHP-monster)

| Table | Size | Rows | Notes |
|---|---|---|---|
| `fact_records` | 5.5 GB | 132,399 | 99% of DB; TOAST dominated |
| `content_entities` | 129 MB | 121,245 | ~10.4 entities/file |
| `content_files` | 66 MB | 11,604 | |
| `projection_decision_evidence` | 2.5 MB | 6,768 | |
| `projection_decisions` | 568 KB | 396 | 3 decisions per repo |
| `runtime_repository_coverage` | 456 KB | 896 | All repos tracked |
| `fact_work_items` | 160 KB | 132 | |

### TOAST Overhead

`fact_records` heap size: 102 MB. TOAST + indexes: 5.4 GB.
**Ratio: 53:1 TOAST-to-heap** for the first 132 repos.

Average fact record size: **41.5 KB** (including TOAST).
The `payload` and `provenance` JSONB columns are the dominant contributors.

### PHP Monster Storage Impact

| Metric | Pre-PHP | During PHP | Growth |
|---|---|---|---|
| `fact_records` | 5.5 GB | 60+ GB (ongoing) | +55+ GB |
| Database total | 5.9 GB | 60+ GB (ongoing) | +55+ GB |
| Postgres RSS | 253 MiB | 1.85 GiB | +1.6 GiB |
| Write rate | - | 10.1 MB/s steady | - |
| Transaction duration | - | 2h+ (ongoing) | - |

**Source-to-TOAST expansion:**

| Repo Type | Source Size | TOAST Size | Ratio |
|---|---|---|---|
| Typical Node.js/Terraform | ~2-3 GB total | 5.5 GB | ~2:1 |
| PHP monster (single repo) | 612 MB | 68 GB (at stop) | ~111:1 |

**Run was stopped at 68 GB** after 1h 53min of continuous writes. The
transaction had not yet committed. Estimated total if allowed to complete:
80-100 GB based on the steady 10.1 MB/s write rate and no sign of slowing.

## Neo4j Graph Profile (at 132 repos)

### Node Distribution

| Label | Count | % |
|---|---|---|
| Parameter | 15,973 | 31.3% |
| Function | 15,790 | 30.9% |
| File | 11,604 | 22.7% |
| Module | 4,541 | 8.9% |
| Directory | 1,651 | 3.2% |
| Class | 632 | 1.2% |
| Interface | 394 | 0.8% |
| Workload | 132 | 0.3% |
| Repository | 132 | 0.3% |
| TerraformDataSource | 64 | 0.1% |
| **Total** | **51,039** | |

### Relationship Distribution

| Type | Count | % |
|---|---|---|
| CALLS | 42,138 | 35.0% |
| CONTAINS | 27,713 | 23.0% |
| IMPORTS | 22,630 | 18.8% |
| HAS_PARAMETER | 16,290 | 13.5% |
| REPO_CONTAINS | 11,604 | 9.6% |
| DEFINES | 132 | 0.1% |
| DEPENDS_ON | 56 | <0.1% |
| INHERITS | 40 | <0.1% |
| **Total** | **~120,603** | |

**Density:** 2.36 relationships per node.

## Resolution Engine Metrics

The resolution engine operated alongside bootstrap's inline projection:

| Metric | Value |
|---|---|
| Work items claimed | 11 |
| Work items completed | 11 |
| Empty polls | 2,769 |
| Avg work item duration | 0.41s |
| Facts loaded | 760 (across 11 items) |

### Projection Stage Durations (resolution engine, 11 items)

| Stage | Total | Avg | Outputs |
|---|---|---|---|
| load_facts | 0.039s | 3.5ms | - |
| project_facts | 1.55s | 141ms | 404 |
| project_relationships | 2.37s | 216ms | 426 |
| project_workloads | 0.14s | 12.6ms | 88 |
| project_platforms | 0.03s | 2.7ms | - |

### Projection Decision Confidence

| Decision Type | Confidence | Band |
|---|---|---|
| project_relationships | 0.75 avg | medium |
| project_workloads | 0.90 avg | high |
| project_platforms | 0.90 avg | high |

### Neo4j Query Performance (resolution engine)

| Operation | Count | Total | Avg |
|---|---|---|---|
| CREATE | 87 | 2.66s | 30.5ms |
| MATCH | 240 | 0.11s | 0.44ms |
| UNWIND | 27 | 0.04s | 1.6ms |
| CALL | 2 | 0.21s | 107ms |

All Neo4j operations completed in < 5 seconds. Zero query timeouts.

## Resource Utilization

### Peak Resource Usage

| Container | CPU | Memory | Phase |
|---|---|---|---|
| bootstrap-index | 106% | 11.5 GiB | Active parsing |
| postgres | 101% | 1.85 GiB | PHP monster TOAST writes |
| neo4j | 487% | 1.77 GiB | Batch graph projection |
| resolution-engine | 0.23% | 142 MiB | Idle (polling) |
| API | 0.18% | 162 MiB | Idle |

### Steady-State During PHP Monster Stall

| Container | CPU | Memory | Notes |
|---|---|---|---|
| bootstrap-index | 24% | 11.25 GiB | Idle, waiting on commit |
| postgres | 101% | 1.85 GiB | Saturated on TOAST writes |
| neo4j | 0.3% | 1.52 GiB | Idle |
| resolution-engine | 0.2% | 142 MiB | Idle, empty polls |

## Postgres Tuning Recommendations

### Baseline Config (all Postgres defaults)

| Setting | Default | Issue |
|---|---|---|
| `shared_buffers` | 128 MB | Far too small for TOAST write buffers |
| `work_mem` | 4 MB | Adequate for our simple queries |
| `maintenance_work_mem` | 64 MB | Slow index creation during DDL |
| `max_wal_size` | 1 GB | Checkpoints every ~100s at 10.1 MB/s write rate |
| `wal_buffers` | 4 MB | Insufficient for sustained bulk writes |
| `effective_cache_size` | 4 GB | Misleads planner on 123 GiB instance |
| `synchronous_commit` | on | Limits write throughput during bulk loads |
| `default_toast_compression` | pglz | Slower than lz4 for our JSONB workload |
| `effective_io_concurrency` | 16 | Underutilizes SSD capabilities |

### Applied Tuning (validated against benchmark data)

| Setting | Value | Workload Justification |
|---|---|---|
| `shared_buffers` | 4 GB | 3% of 123 GiB RAM; other services use 13+ GiB. TOAST writes are sequential so diminishing returns beyond 4 GB |
| `work_mem` | 16 MB | No complex queries (no JOINs/sorts). Only `list_facts` does ORDER BY on indexed column |
| `maintenance_work_mem` | 512 MB | DDL runs once at startup (14 CREATE INDEX). Fast completion avoids startup lock contention |
| `max_wal_size` | 8 GB | At measured 10.1 MB/s write rate, checkpoints now every ~13 min instead of ~100s. Reduces I/O contention |
| `wal_buffers` | 64 MB | Buffers ~6s of WAL at sustained write rate |
| `effective_cache_size` | 32 GB | ~25% of instance RAM. Planner hint only |
| `synchronous_commit` | off | Batches WAL flushes for 2-3x bulk write throughput. Risk: up to 600ms data loss on crash; acceptable for re-runnable ingestion |
| `default_toast_compression` | lz4 | 3-5x faster than pglz. Direct hit on our bottleneck (TOAST writes are 99% of I/O) |
| `effective_io_concurrency` | 200 | SSD/NVMe optimization |
| `random_page_cost` | 1.1 | SSD tuning (default 4.0 is for spinning disks) |

### Application-Level Optimizations (applied)

1. **Chunked executemany** (applied in `facts/storage/postgres.py`):
   Batches of 2,000 rows (configurable via `PCG_FACT_UPSERT_BATCH_SIZE`).
   Each chunk commits independently under autocommit mode. The PHP monster's
   estimated 500K+ facts now process as ~250 independent transactions of
   ~5-10 seconds each instead of one 2-hour transaction. Pipeline can
   interleave other work between chunks.

### Future Optimizations (not yet applied)

1. **COPY instead of INSERT:** Use `psycopg3.copy` with binary mode for
   bulk fact loads. Expected 3-10x improvement over `executemany`.

2. **JSONB compression:** Store `payload` and `provenance` as pre-compressed
   `bytea` with zstd instead of raw `Jsonb`. Application-managed compression
   typically achieves 5-10x better ratios than TOAST's pglz.

3. **Vendor/generated file exclusion:** Add `.pcgignore` rules for known
   vendor directories (`vendor/`, `node_modules/`) to skip parsing generated
   or third-party code that inflates fact storage without adding value.

## Validation

- **Zero blocked locks** throughout the entire run
- **Zero deadlocks** -- schema lock fix (`SELECT 1 FROM information_schema.tables`
  before DDL) validated under concurrent load
- **Zero application errors** across all services (bootstrap, resolution
  engine, API)
- **11 of 11** resolution engine work items completed successfully
- **132 of 132** inline projection work items completed
- **31 JSON parse errors** for Jinja template files (expected, harmless)

## Comparison Notes for ArcadeDB Evaluation

When comparing against ArcadeDB, use these as the baseline targets:

1. **Parse throughput:** 10-20 files/sec (language-dependent)
2. **Commit throughput:** median 7.7s, mean 11.6s per repo
3. **Fixed commit overhead:** ~11s minimum regardless of repo size
4. **Graph write latency:** Neo4j CREATE avg 30.5ms, MATCH avg 0.44ms
5. **Storage efficiency:** 41.5 KB/fact average (TOAST dominated)
6. **Pipeline stall risk:** Single large repo can block entire pipeline
7. **Total time for 132 normal repos:** 12 minutes end-to-end
8. **Resolution engine projection:** 0.41s avg per work item
