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
| **`PARALLEL_WORKERS`** | `4` | Legacy fallback for parse-worker count when `PCG_PARSE_WORKERS` is unset. |
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

### Concurrency And Watch Controls

These settings are the public knobs for the checkpointed Python indexing pipeline and repo-partitioned watch loop.

| Key | Default | Description |
| :--- | :--- | :--- |
| **`PCG_PARSE_WORKERS`** | `4` | Number of concurrent repository parse workers used by checkpointed indexing. |
| **`PCG_REPO_FILE_PARSE_MULTIPROCESS`** | `false` | When `true`, file parsing inside a repository snapshot uses a process pool instead of the threaded path. |
| **`PCG_MULTIPROCESS_START_METHOD`** | `spawn` | Process start method for parse workers. `spawn` is the safe default for host and container runtimes; override only after verifying another mode on your exact platform. |
| **`PCG_WORKER_MAX_TASKS`** | unset | Optional per-worker recycle threshold for the multiprocess parser. Leave unset to keep workers alive for the whole run; set it only if you need explicit worker recycling for a known memory issue. |
| **`PCG_INDEX_QUEUE_DEPTH`** | `8` | Maximum number of parsed repositories allowed to wait for commit/finalization. |
| **`PCG_WATCH_DEBOUNCE_SECONDS`** | `2.0` | Debounce interval for batching file-system events before incremental updates run. |

Notes:

- `PCG_PARSE_WORKERS` is the primary worker control for modern multi-repo indexing.
- `PCG_REPO_FILE_PARSE_MULTIPROCESS` enables the process-pool parse engine; leave it `false` until you want the heavier worker-process path.
- `PCG_MULTIPROCESS_START_METHOD` now defaults to `spawn` because it is the most reliable choice for the parser-heavy process-pool path across local macOS and Linux containers.
- `PCG_WORKER_MAX_TASKS` is now opt-in. The default leaves parse workers alive for the whole run because recycling long-lived parser workers can stall large local and containerized indexing jobs.
- `PARALLEL_WORKERS` is still honored as a backward-compatible fallback when `PCG_PARSE_WORKERS` is not set.
- `pcg index` and `pcg watch` now print the effective worker/debounce values they are using so local runs match the documented configuration.

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

### Ingester Runtime

These settings matter for deployable-service installs that use the repository ingester runtime.

| Key | Default | Description |
| :--- | :--- | :--- |
| **`PCG_RUNTIME_ROLE`** | `combined` | Runtime identity. Deployed split runtimes use `api` or `ingester`. |
| **`PCG_REPO_SOURCE_MODE`** | `githubOrg` | Repository discovery mode. Supported modes include `githubOrg`, `explicit`, and `filesystem`. |
| **`PCG_GITHUB_ORG`** | unset | GitHub organization used for repository discovery in `githubOrg` mode. |
| **`PCG_REPOSITORY_RULES_JSON`** | unset | Structured exact/regex include rules applied to normalized `org/repo` identifiers during repo rediscovery. |
| **`PCG_REPOSITORIES`** | unset | Deprecated exact-repository shorthand. Prefer `PCG_REPOSITORY_RULES_JSON`. |
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
- `index` indexes the materialized `PCG_REPOS_DIR` workspace using the same shared Python indexing path as manual local indexing
- `status` reports the configured workspace path plus the latest checkpointed workspace index summary
- `watch` watches the materialized workspace in repo-partitioned mode and can optionally rediscover newly added repos with `--sync-interval-seconds`

Path-first commands such as `pcg index <path>` and `pcg watch <path>` still work as
local filesystem convenience wrappers. They do not replace the canonical workspace
source model.
