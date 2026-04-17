# Configuration & Settings

PlatformContextGraph is highly configurable through environment files and the CLI.

## `pcg config` Command

View and modify settings directly from the terminal.

### 1. View Settings
Shows the current effective configuration (merged from defaults and `.env`).

```bash
pcg config show
```

### 2. Set a Value
Update a setting permanently. This writes to `~/.platform-context-graph/.env`.

**Syntax:** `pcg config set <KEY> <VALUE>`

```bash
# Switch to Neo4j backend
pcg config set DEFAULT_DATABASE neo4j

# Increase max file size to index (MB)
pcg config set MAX_FILE_SIZE_MB 20

# Enable automatic watching after index
pcg config set ENABLE_AUTO_WATCH true
```

The user-level `~/.platform-context-graph/.env` file is for CLI settings, not
the local API bearer-token contract. When local compose auth is enabled, the
Go API and MCP runtimes use `PCG_API_KEY` from the running container
environment.

### 3. Quick Switch Database
A shortcut to toggle between `falkordb` and `neo4j`.

```bash
pcg config db neo4j
```

---

## Configuration Reference

Here are the available settings you can configure.

### Core Settings

| Key | Default | Description |
| :--- | :--- | :--- |
| **`DEFAULT_DATABASE`** | `falkordb` | The database engine to use (`neo4j`, `falkordb`, or `kuzudb`). |
| **`ENABLE_AUTO_WATCH`** | `false` | If `true`, `pcg index` will automatically start watching for changes. |
| **`CACHE_ENABLED`** | `true` | Caches file hashes to speed up re-indexing. |

### Logging And Tracing

These settings control the shared structured logging and OTEL tracing behavior used by the API, MCP runtime, ingester, Falkor worker, and local CLI.

| Key | Default | Description |
| :--- | :--- | :--- |
| **`PCG_LOG_FORMAT`** | `json` | Log output format. `json` is the production standard. `text` is only for local debugging. |
| **`ENABLE_APP_LOGS`** | `INFO` | Application log threshold (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, `DISABLED`). |
| **`LIBRARY_LOG_LEVEL`** | `WARNING` | Log threshold for noisy third-party libraries such as `neo4j`, `asyncio`, and `urllib3`. |
| **`DEBUG_LOGS`** | `false` | Enables the legacy debug-file sink. When enabled, it writes the same JSON envelope used on stdout. |
| **`DEBUG_LOG_PATH`** | `~/mcp_debug.log` | Legacy debug-file path used only when `DEBUG_LOGS=true`. |
| **`LOG_FILE_PATH`** | app home logs path | Optional structured file sink for process logs. Stdout JSON is still the canonical output. |

Notes:

- The default production shape is JSON on stdout plus OTEL traces over OTLP.
- Logs are intentionally shaped for generic collectors. Loki, Elasticsearch, and similar backends can treat each line as one JSON document.
- Every log record uses the same top-level envelope and stores custom dimensions under `extra_keys`.
- Trace correlation is automatic when a log is emitted inside an active OTEL span.
- The request ID becomes the default correlation ID unless an upstream correlation ID is already present.
- OTEL logs export is not required for this setup. Stdout JSON is the source of truth for logs.

### Concurrency Controls

These settings are the public knobs for the Go-owned collector, projector,
bootstrap, reducer, and watch flows.

| Key | Default | Description |
| :--- | :--- | :--- |
| **`PCG_SNAPSHOT_WORKERS`** | `min(NumCPU, 8)` | Concurrent repository snapshot workers for collector/bootstrap discovery and collection. |
| **`PCG_PARSE_WORKERS`** | `min(NumCPU, 8)` | Concurrent file-parse workers inside a repository snapshot. |
| **`PCG_STREAM_BUFFER`** | `0` | Optional buffer for streaming collected generations. `0` means use the worker-count-derived default. |
| **`PCG_LARGE_REPO_FILE_THRESHOLD`** | `1000` | File-count threshold above which a repository is treated as “large” for concurrency limiting. |
| **`PCG_LARGE_REPO_MAX_CONCURRENT`** | `2` | Maximum number of large repositories that may be snapshotted concurrently. |
| **`PCG_PROJECTOR_WORKERS`** | `min(NumCPU, 8)` | Concurrent source-local projection workers in the ingester runtime. |
| **`PCG_LARGE_GEN_THRESHOLD`** | `10000` | Fact-count threshold above which a projector generation is treated as “large”. |
| **`PCG_LARGE_GEN_MAX_CONCURRENT`** | `2` | Maximum number of large projector generations processed concurrently. |
| **`PCG_PROJECTION_WORKERS`** | `min(NumCPU, 8)` | Concurrent bootstrap-index projection workers. |
| **`PCG_REDUCER_WORKERS`** | `min(NumCPU, 4)` | Concurrent reducer intent workers in the resolution engine. |
| **`PCG_REDUCER_BATCH_CLAIM_SIZE`** | `workers * 4` (min 4, max 64) | Number of reducer intents claimed per polling cycle. |
| **`PCG_SHARED_PROJECTION_WORKERS`** | `1` | Concurrent shared-projection partition workers. |
| **`PCG_SHARED_PROJECTION_PARTITION_COUNT`** | `8` | Number of shared-projection partitions per domain. |
| **`PCG_SHARED_PROJECTION_BATCH_LIMIT`** | `100` | Maximum intents processed per shared-projection partition batch. |
| **`PCG_SHARED_PROJECTION_POLL_INTERVAL`** | `5s` | Idle poll interval for shared projection work. |
| **`PCG_SHARED_PROJECTION_LEASE_TTL`** | `60s` | Lease duration for shared-projection partition claims. |

Removed Python-era parser controls:

- `PCG_REPO_FILE_PARSE_MULTIPROCESS`
- `PCG_MULTIPROCESS_START_METHOD`
- `PCG_WORKER_MAX_TASKS`
- `PCG_INDEX_QUEUE_DEPTH`
- `PCG_WATCH_DEBOUNCE_SECONDS`

`pcg index` launches the Go `bootstrap-index` runtime in direct filesystem
mode, and `pcg watch` hands off to the Go ingester runtime. Neither command
uses the deleted Python multiprocess parser controls anymore.

### Indexing Scope

| Key | Default | Description |
| :--- | :--- | :--- |
| **`MAX_FILE_SIZE_MB`** | `5` | Files larger than this (in MB) are skipped. |
| **`IGNORE_TESTS`** | `false` | If `true`, skips folders named `tests` or `spec`. |
| **`IGNORE_HIDDEN`** | `true` | Skips hidden files (`.git`, `.vscode`). |
| **`IGNORE_DIRS`** | built-in list | Comma-separated directory names that PCG always skips before descent. Defaults include `.git`, common virtualenv roots, and generic build caches. |
| **`PCG_IGNORE_DEPENDENCY_DIRS`** | `true` | Excludes built-in dependency and tool-managed cache roots such as `vendor/`, `node_modules/`, `site-packages/`, `deps/`, `.terraform/`, and `.terragrunt-cache/` before parse and storage. |
| **`INDEX_VARIABLES`** | `true` | Creates nodes for variables. Set to `false` for a smaller graph. |

### Database Connection (Neo4j)

| Key | Description |
| :--- | :--- |
| **`NEO4J_URI`** | Connection URI (e.g., `bolt://localhost:7687`). |
| **`NEO4J_USERNAME`** | Database user (default: `neo4j`). |
| **`NEO4J_PASSWORD`** | Database password. |

### Go Runtime Database Tuning

These settings are consumed by the Go runtime data plane and are especially
useful for split-service Kubernetes deployments where API, ingester, and
resolution-engine workloads should be tuned independently.

| Key | Default | Description |
| :--- | :--- | :--- |
| **`PCG_POSTGRES_MAX_OPEN_CONNS`** | runtime default | Maximum open PostgreSQL connections for Go runtimes. |
| **`PCG_POSTGRES_MAX_IDLE_CONNS`** | runtime default | Maximum idle PostgreSQL connections for Go runtimes. |
| **`PCG_POSTGRES_CONN_MAX_LIFETIME`** | runtime default | Maximum lifetime for one PostgreSQL connection. |
| **`PCG_POSTGRES_CONN_MAX_IDLE_TIME`** | runtime default | Maximum idle lifetime for one PostgreSQL connection. |
| **`PCG_POSTGRES_PING_TIMEOUT`** | runtime default | Timeout used when a Go runtime verifies PostgreSQL connectivity during startup. |
| **`PCG_NEO4J_MAX_CONNECTION_POOL_SIZE`** | runtime default | Maximum Neo4j driver pool size for Go runtimes. |
| **`PCG_NEO4J_MAX_CONNECTION_LIFETIME`** | runtime default | Maximum lifetime for one Neo4j driver connection. |
| **`PCG_NEO4J_CONNECTION_ACQUISITION_TIMEOUT`** | runtime default | Timeout while waiting for a Neo4j pooled connection. |
| **`PCG_NEO4J_SOCKET_CONNECT_TIMEOUT`** | runtime default | Timeout for establishing a Neo4j socket connection. |
| **`PCG_NEO4J_VERIFY_TIMEOUT`** | runtime default | Timeout used when a Go runtime verifies Neo4j connectivity during startup. |

### Content Store And Source Retrieval

| Key | Default | Description |
| :--- | :--- | :--- |
| **`PCG_CONTENT_STORE_ENABLED`** | `true` | Enables PostgreSQL-backed content retrieval and search. Set this to `false` to disable Postgres content access entirely. |
| **`PCG_CONTENT_STORE_DSN`** | unset | Primary DSN for the PostgreSQL content store. |
| **`PCG_POSTGRES_DSN`** | unset | Backward-compatible alias for the PostgreSQL content store DSN. |
| **`PCG_FACT_STORE_DSN`** | unset | Primary DSN for the facts-first PostgreSQL fact store. Falls back to `PCG_CONTENT_STORE_DSN` or `PCG_POSTGRES_DSN` when unset. |
| **`PCG_FACT_STORE_POOL_MAX_SIZE`** | `4` | Maximum psycopg pool size for the fact-store backend. |
| **`PCG_FACT_QUEUE_POOL_MAX_SIZE`** | `4` | Maximum psycopg pool size for the facts work-queue backend. |

Notes:

- deployed API runtimes use the PostgreSQL content store directly and return `unavailable` when content is not yet indexed
- facts-first Git ingestion also uses Postgres for fact persistence and queued projection work
- local helper flows may still fall back to the workspace or graph cache
- content search routes and MCP search tools require PostgreSQL and return an error when the content store is disabled
- portable source retrieval uses `repo_id + relative_path` for files and `entity_id` for content-bearing entities
- the Helm chart exposes Go runtime pool tuning per workload under `api.connectionTuning`, `ingester.connectionTuning`, and `resolutionEngine.connectionTuning`

### Ingester Runtime

These settings matter for deployable-service installs that use the repository ingester runtime.

| Key | Default | Description |
| :--- | :--- | :--- |
| **`PCG_RUNTIME_ROLE`** | `combined` | Internal runtime identity. Deployed split runtimes use `api` or `ingester`; the public service name for that second runtime is the ingester. |
| **`PCG_REPO_SOURCE_MODE`** | `githubOrg` | Repository discovery mode. Supported modes include `githubOrg`, `explicit`, and `filesystem`. |
| **`PCG_GITHUB_ORG`** | unset | GitHub organization used for repository discovery in `githubOrg` mode. |
| **`PCG_REPOSITORY_RULES_JSON`** | unset | Structured exact/regex include rules applied to normalized `org/repo` identifiers during repo rediscovery. Exact rules also define repository IDs for `explicit` and `filesystem` source modes. |
| **`PCG_REPOS_DIR`** | `/data/repos` | Shared workspace directory for cloned repositories. |
| **`PCG_REPO_LIMIT`** | `4000` | Maximum repositories to discover from GitHub in one cycle. |
| **`PCG_REPO_SYNC_INITIAL_DELAY_SECONDS`** | `30` | Delay before the ingester begins its first sync cycle. |
| **`PCG_REPO_SYNC_INTERVAL_SECONDS`** | `900` | Delay between ingester sync cycles after a completed pass. |

`PCG_REPOSITORY_RULES_JSON` accepts either a list of rules or an object with `exact` and `regex` keys. Example:

```json
[
  {"exact": "platformcontext/platform-context-graph"},
  {"regex": "platformcontext/(payments|orders)-.*"}
]
```

The repository ingester re-discovers repositories on each cycle, applies these rules, updates matching checkouts, and reports stale local checkouts that no longer match the discovery result.

---

## Configuration Files

PlatformContextGraph uses the following hierarchy:

1.  **Project Level:** `.pcgignore` in your project root (files to exclude).
2.  **User Level:** `~/.platform-context-graph/.env` (global settings).
3.  **Defaults:** Built-in application defaults.

That user-level `.env` file is for CLI configuration. It is not the local API
bearer-token store; the Go API and MCP runtimes read `PCG_API_KEY` from their
own process environment when bearer auth is enabled.

Use `.pcgignore` for project-specific exclusions. Use
`PCG_IGNORE_DEPENDENCY_DIRS` to control the built-in dependency-root policy, and
use `IGNORE_DIRS` only if you want to change the generic always-ignore
directory list globally.

For logging, the rule is simpler: keep `PCG_LOG_FORMAT=json` unless you are
debugging locally and want a human-readable stream.

To reset everything to defaults:
```bash
pcg config reset
```

## `pcg workspace` Commands

Use the workspace command group when you want local CLI behavior to follow the same
repository-source contract as the cloud ingester.

```bash
pcg workspace plan
pcg workspace sync
pcg workspace index
pcg workspace status
pcg workspace watch
```

- `plan` previews the repositories selected by the current source configuration
- `sync` materializes the matching repositories into `PCG_REPOS_DIR` without starting a manual index run
- `index` launches the Go `bootstrap-index` runtime against the configured
  workspace using direct filesystem mode, so local workspace indexing follows
  the same Go-owned parser and write path as the deployed data plane
- `status` reports the configured workspace path plus the latest checkpointed workspace index summary
- `watch` watches the materialized workspace in repo-partitioned mode and can optionally rediscover newly added repos with `--sync-interval-seconds`

Path-first commands such as `pcg index <path>` and `pcg watch <path>` still work as
local filesystem convenience wrappers. `pcg index` now shells into the Go
`bootstrap-index` runtime with a persistent state directory under `PCG_HOME`,
while `pcg watch` remains the local incremental convenience surface. They do not
replace the canonical workspace source model.

## Recovery Commands

Recovery surfaces still exist for operator use, but they are Go-owned repair
endpoints rather than a separate runtime model.

- `pcg finalize` has been removed. Recovery is owned by the Go ingester at
  `/admin/refinalize` and `/admin/replay`.
- Recovery no longer depends on bridge stages or Python post-commit ownership.
- `pcg workspace index` and `pcg workspace watch` remain valuable for local
  proof and workstation workflows, but the canonical deployed write plane is
  still the split `ingester` plus `resolution-engine` runtime model.

If you are tuning or operating a deployed environment, start with the runtime
and queue settings for the service you are scaling. Use the repair commands
only when you are intentionally replaying or recovering already-collected data.
