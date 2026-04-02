"""Static configuration catalog metadata for PlatformContextGraph."""

from __future__ import annotations

from pathlib import Path

from ..paths import get_app_env_file, get_app_home

CONFIG_DIR = get_app_home()
CONFIG_FILE = get_app_env_file()

DATABASE_CREDENTIAL_KEYS = {
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
}

DEFAULT_CONFIG = {
    "DEFAULT_DATABASE": "falkordb",
    "FALKORDB_PATH": str(CONFIG_DIR / "falkordb.db"),
    "FALKORDB_SOCKET_PATH": str(CONFIG_DIR / "falkordb.sock"),
    "INDEX_VARIABLES": "false",
    "PCG_VARIABLE_SCOPE": "module",
    "ALLOW_DB_DELETION": "false",
    "DEBUG_LOGS": "false",
    "DEBUG_LOG_PATH": str(Path.home() / "mcp_debug.log"),
    "ENABLE_APP_LOGS": "INFO",
    "LIBRARY_LOG_LEVEL": "WARNING",
    "PCG_LOG_FORMAT": "json",
    "LOG_FILE_PATH": str(CONFIG_DIR / "logs" / "pcg.log"),
    "MAX_FILE_SIZE_MB": "10",
    "IGNORE_TEST_FILES": "false",
    "IGNORE_HIDDEN_FILES": "true",
    "ENABLE_AUTO_WATCH": "false",
    "COMPLEXITY_THRESHOLD": "10",
    "MAX_DEPTH": "unlimited",
    "PARALLEL_WORKERS": "4",
    "PCG_PARSE_WORKERS": "4",
    "PCG_REPO_FILE_PARSE_MULTIPROCESS": "false",
    "PCG_MULTIPROCESS_START_METHOD": "spawn",
    "PCG_WORKER_MAX_TASKS": "",
    "PCG_REPO_FILE_PARSE_CONCURRENCY": "1",
    "PCG_COMMIT_WORKERS": "1",
    "PCG_INDEX_QUEUE_DEPTH": "8",
    "PCG_MAX_ENTITY_VALUE_LENGTH": "200",
    "PCG_HONOR_GITIGNORE": "true",
    "PCG_WATCH_DEBOUNCE_SECONDS": "2.0",
    "PCG_ENABLE_PUBLIC_DOCS": "true",
    "CACHE_ENABLED": "true",
    "IGNORE_DIRS": "venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,__pycache__,.terraform,.terragrunt-cache,.terramate-cache,.pulumi,.crossplane,.serverless,.aws-sam,cdk.out",
    "INDEX_SOURCE": "true",
    "SCIP_INDEXER": "false",
    "SCIP_LANGUAGES": "python,typescript,go,rust,java",
    "SKIP_EXTERNAL_RESOLUTION": "false",
    "INDEX_JSON": "true",
    "INDEX_YAML": "true",
    "INDEX_HCL": "true",
    "PCG_IGNORE_DEPENDENCY_DIRS": "true",
    "PCG_MAX_CALLS_PER_FILE": "50",
    "PCG_CALL_RESOLUTION_SCOPE": "repo",
    "PCG_ASYNC_COMMIT_ENABLED": "false",
    "PCG_COMMIT_GIL_YIELD_ENABLED": "true",
    "PCG_INDEX_SUMMARY_DIR": "",
    "ECOSYSTEM_MANIFEST_PATH": "",
    "ECOSYSTEM_BASE_PATH": "",
    "ECOSYSTEM_PARALLEL_REPOS": "4",
}

CONFIG_DESCRIPTIONS = {
    "DEFAULT_DATABASE": "Default database backend (neo4j|falkordb|kuzudb)",
    "FALKORDB_PATH": "Path to FalkorDB database file",
    "FALKORDB_SOCKET_PATH": "Path to FalkorDB Unix socket",
    "INDEX_VARIABLES": "Index variable nodes in the graph (lighter graph if false)",
    "PCG_VARIABLE_SCOPE": "Scope filter for variable extraction: 'module' (module/class-level only) or 'all' (every assignment)",
    "ALLOW_DB_DELETION": "Allow full database deletion commands",
    "DEBUG_LOGS": "Enable debug logging (for development/troubleshooting)",
    "DEBUG_LOG_PATH": "Legacy path to the structured debug log file when DEBUG_LOGS=true",
    "ENABLE_APP_LOGS": "Application log level (DEBUG|INFO|WARNING|ERROR|CRITICAL|DISABLED)",
    "LIBRARY_LOG_LEVEL": "Log level for third-party libraries (neo4j, asyncio, urllib3) (DEBUG|INFO|WARNING|ERROR|CRITICAL)",
    "PCG_LOG_FORMAT": "Application log format (json|text); json is the default and production standard",
    "LOG_FILE_PATH": "Legacy path to the structured application log file",
    "MAX_FILE_SIZE_MB": "Maximum file size to index (in MB)",
    "IGNORE_TEST_FILES": "Skip test files during indexing",
    "IGNORE_HIDDEN_FILES": "Skip hidden files/directories",
    "ENABLE_AUTO_WATCH": "Automatically watch directory after indexing",
    "COMPLEXITY_THRESHOLD": "Cyclomatic complexity warning threshold",
    "MAX_DEPTH": "Maximum directory depth for indexing (unlimited or number)",
    "PARALLEL_WORKERS": "Legacy fallback for parse workers when PCG_PARSE_WORKERS is unset",
    "PCG_PARSE_WORKERS": "Number of concurrent repository parse workers for checkpointed indexing",
    "PCG_REPO_FILE_PARSE_MULTIPROCESS": "Enable process-pool file parsing within repository snapshot builds",
    "PCG_MULTIPROCESS_START_METHOD": "Multiprocessing start method for parse workers (spawn recommended for local and containerized indexing)",
    "PCG_WORKER_MAX_TASKS": "Optional worker recycle threshold for process-pool file parsers; leave unset to disable recycling",
    "PCG_REPO_FILE_PARSE_CONCURRENCY": "Opt-in number of files to parse concurrently within a single repository snapshot",
    "PCG_COMMIT_WORKERS": "Number of concurrent commit consumers draining the snapshot queue (each repo commits to its own subgraph; default 1 preserves serial behavior)",
    "PCG_INDEX_QUEUE_DEPTH": "Maximum queued parsed repositories waiting to commit",
    "PCG_MAX_ENTITY_VALUE_LENGTH": "Maximum number of characters preserved for graph entity value previews before truncation",
    "PCG_HONOR_GITIGNORE": "Honor repo-local .gitignore files during repo/workspace indexing and watch scans",
    "PCG_WATCH_DEBOUNCE_SECONDS": "Debounce interval in seconds for watcher update batches",
    "PCG_ENABLE_PUBLIC_DOCS": "Expose unauthenticated OpenAPI, Swagger UI, and ReDoc endpoints for the HTTP API",
    "CACHE_ENABLED": "Enable caching for faster re-indexing",
    "IGNORE_DIRS": "Comma-separated list of directory names to ignore during indexing",
    "PCG_IGNORE_DEPENDENCY_DIRS": "Exclude built-in vendored/dependency and tool-managed cache directories before parse and storage",
    "PCG_MAX_CALLS_PER_FILE": (
        "Maximum function calls per file to resolve during finalization. "
        "Controls the tradeoff between CALLS edge completeness and finalization speed. "
        "Lower values (25-50) make finalization fast but may miss some cross-function edges "
        "in large files. Higher values (200-500) capture more edges but can cause finalization "
        "to stall on repos with many large JS/PHP files — each call generates a Cypher query "
        "against Neo4j. Files exceeding this cap have their remaining calls silently dropped. "
        "The default of 50 covers the high-signal contextual calls (same-file and import-linked) "
        "for typical source files. Increase for codebases where deep cross-file call graphs "
        "are critical; decrease for large monorepos with many utility/vendor files."
    ),
    "PCG_CALL_RESOLUTION_SCOPE": (
        "Scope for function-call resolution during finalization (repo|global). "
        "When 'repo', unresolved calls are matched by name only within the same "
        "repository (path prefix), preventing cross-repo name-guessing. "
        "When 'global', unresolved calls fall through to corpus-wide name matching "
        "(original behavior). The default 'repo' improves both precision and speed "
        "for multi-repo workspaces."
    ),
    "PCG_ASYNC_COMMIT_ENABLED": (
        "Use per-batch async commit path instead of asyncio.to_thread(). "
        "Each file batch runs in a dedicated single-thread executor with "
        "event-loop yielding between batches, enabling true parallel "
        "commit workers without GIL contention. Default false — enable "
        "after validating with PCG_COMMIT_WORKERS>1."
    ),
    "PCG_COMMIT_GIL_YIELD_ENABLED": (
        "Insert time.sleep(0) after each Neo4j tx.commit() to voluntarily "
        "release the Python GIL, allowing the asyncio event loop to schedule "
        "other commit workers. Required for PCG_COMMIT_WORKERS>1 to achieve "
        "actual parallelism via asyncio.to_thread()."
    ),
    "PCG_INDEX_SUMMARY_DIR": (
        "Override directory for run summary JSON artifacts. "
        "When unset, summaries are written to ~/.pcg/index-runs/<run_id>/."
    ),
    "INDEX_SOURCE": "Store full source code in graph database (for faster indexing use false, for better performance use true)",
    "SCIP_INDEXER": "Use SCIP-based indexing for higher accuracy call/inheritance resolution (requires scip-<lang> tools installed)",
    "SCIP_LANGUAGES": "Comma-separated languages to index via SCIP when SCIP_INDEXER=true (python,typescript,go,rust,java)",
    "SKIP_EXTERNAL_RESOLUTION": "Skip resolution attempts for external library method calls (recommended for enterprise large Java/Spring codebases)",
    "INDEX_JSON": "Index targeted JSON config files (package.json, composer.json, tsconfig.json, and JSON CloudFormation templates)",
    "INDEX_YAML": "Index YAML infrastructure files (K8s, ArgoCD, Crossplane, Helm, Kustomize)",
    "INDEX_HCL": "Index HCL/Terraform infrastructure files (.tf, .hcl)",
    "ECOSYSTEM_MANIFEST_PATH": "Path to ecosystem dependency-graph.yaml manifest",
    "ECOSYSTEM_BASE_PATH": "Base directory where ecosystem repos are cloned",
    "ECOSYSTEM_PARALLEL_REPOS": "Number of repos to index in parallel during ecosystem indexing",
}

CONFIG_VALIDATORS = {
    "DEFAULT_DATABASE": ["neo4j", "falkordb", "kuzudb"],
    "INDEX_VARIABLES": ["true", "false"],
    "PCG_VARIABLE_SCOPE": ["module", "all"],
    "ALLOW_DB_DELETION": ["true", "false"],
    "DEBUG_LOGS": ["true", "false"],
    "ENABLE_APP_LOGS": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "DISABLED"],
    "LIBRARY_LOG_LEVEL": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    "PCG_LOG_FORMAT": ["json", "text"],
    "IGNORE_TEST_FILES": ["true", "false"],
    "IGNORE_HIDDEN_FILES": ["true", "false"],
    "ENABLE_AUTO_WATCH": ["true", "false"],
    "CACHE_ENABLED": ["true", "false"],
    "INDEX_SOURCE": ["true", "false"],
    "SCIP_INDEXER": ["true", "false"],
    "SKIP_EXTERNAL_RESOLUTION": ["true", "false"],
    "PCG_HONOR_GITIGNORE": ["true", "false"],
    "PCG_ENABLE_PUBLIC_DOCS": ["true", "false"],
    "PCG_REPO_FILE_PARSE_MULTIPROCESS": ["true", "false"],
    "PCG_MULTIPROCESS_START_METHOD": ["spawn", "fork", "forkserver"],
    "PCG_IGNORE_DEPENDENCY_DIRS": ["true", "false"],
    "PCG_CALL_RESOLUTION_SCOPE": ["repo", "global"],
    "PCG_ASYNC_COMMIT_ENABLED": ["true", "false"],
    "PCG_COMMIT_GIL_YIELD_ENABLED": ["true", "false"],
    "INDEX_JSON": ["true", "false"],
    "INDEX_YAML": ["true", "false"],
    "INDEX_HCL": ["true", "false"],
}

__all__ = [
    "CONFIG_DESCRIPTIONS",
    "CONFIG_DIR",
    "CONFIG_FILE",
    "CONFIG_VALIDATORS",
    "DATABASE_CREDENTIAL_KEYS",
    "DEFAULT_CONFIG",
]
