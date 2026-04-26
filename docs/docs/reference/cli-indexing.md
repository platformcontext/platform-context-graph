# CLI: Indexing & Management

These commands are the foundation of PlatformContextGraph. They allow you to add, remove, and monitor the code repositories in your graph.

## `pcg index`

Adds a code repository to the graph database. This is the first step for any project.

For directory and workspace targets, this command launches the
`bootstrap-index` runtime in direct filesystem mode.

!!! info "Excluding Files (.pcgignore)"
    PCG already skips hidden and well-known cache directories such as `.git`, `.terraform`, `.terragrunt-cache`, `.pulumi`, `.crossplane`, `.serverless`, `.aws-sam`, and `cdk.out`.
    It also excludes built-in dependency roots such as `vendor/`, `node_modules/`, `site-packages/`, and `deps/` before parse by default.
    Use `.pcgignore` for project-specific exclusions beyond those built-in defaults.
    **[📄 Read the .pcgignore Guide](pcgignore.md)**

**Usage:**
```bash
pcg index [path] [options]
```

**Common Options:**

*   `path`: The folder to index (default: current directory).
*   `--force`: Re-index from scratch, even if it looks unchanged.
*   `--discovery-report <file>`: Write a JSON discovery advisory report for
    noisy-repo tuning. The report lists discovered, parsed, skipped, and
    materialized file/entity counts plus top noisy directories/files and skip
    breakdowns. It is an operator artifact, not a high-cardinality metric.

**Runtime Notes:**

*   Local index state for the Go launcher is stored under `PCG_HOME/state/go-bootstrap-index/`.
*   `--discovery-report` forwards `PCG_DISCOVERY_REPORT=<absolute path>` to
    `bootstrap-index`, which writes one JSON array containing an advisory per
    collected repository.
*   When using the lightweight local host (`pcg watch`, `pcg mcp stdio`),
    per-workspace state lives under
    `${PCG_HOME}/local/workspaces/<workspace_id>/`. Workspace-root resolution
    order and data-root layout are documented in
    [CLI Reference — Workspace root and profiles](cli-reference.md#workspace-root-and-profiles)
    and [Local Data Root Spec](local-data-root-spec.md).
*   The command still honors `.gitignore`, `.pcgignore`, and the configured parse-worker settings.

**Example:**
```bash
# Index the current folder
$ pcg index .

# Index a specific project
$ pcg index /home/user/projects/backend-api
```

---

## `pcg list`

Shows all repositories currently stored in your graph database.

**Usage:**
```bash
pcg list
```

**Example Output:**
```text
Indexed Repositories:
1. /home/user/projects/backend-api (Nodes: 1205)
2. /home/user/projects/frontend-ui (Nodes: 850)
```

---

## `pcg watch`

Starts a real-time monitor. If you edit a file, the graph updates instantly.

The watch path runs end to end through the current local refresh flow:

- when the watched repo or workspace is missing index state, the initial scan
  launches the Go `bootstrap-index` runtime
- after startup, filesystem events are debounced into repo-level reindex runs
  through the same indexing path

!!! warning "Foreground Process"
    This command runs in the foreground. Open a new terminal tab to keep it running.

**Usage:**
```bash
pcg watch [path]
```

**Example:**
```bash
$ pcg watch .
[INFO] Watching /home/user/projects/backend-api for changes...
[INFO] Detected change in users/models.py. Re-indexing...
```

This is the CLI-friendly local equivalent of the long-running sync and re-index loop used in the deployable-service runtime.

For multi-repository local indexing, use `pcg workspace index`. The public Go
CLI keeps ecosystem-wide indexing on the `workspace` and admin flows rather
than on separate ecosystem indexing commands.

---

## Compatibility Stubs

The current Go CLI still carries a few compatibility stubs so older operator
muscle memory gets a directed error instead of a silent behavior change:

- `pcg delete`
- `pcg clean`
- `pcg add-package`
- `pcg ecosystem index`
- `pcg ecosystem status`

Deletion, cleanup, and recovery are owned by the Go admin/runtime surfaces
rather than ad hoc local CLI mutations.

---

## Related docs

- [Troubleshooting](troubleshooting.md)
