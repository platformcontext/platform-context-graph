# CLI: Indexing & Management

These commands are the foundation of PlatformContextGraph. They allow you to add, remove, and monitor the code repositories in your graph.

## `pcg index`

Adds a code repository to the graph database. This is the first step for any project.

For directory and workspace targets, this command now launches the Go-owned
`bootstrap-index` runtime in direct filesystem mode instead of the legacy Python
parser/coordinator path.

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

**Runtime Notes:**

*   Local index state for the Go launcher is stored under `PCG_HOME/state/go-bootstrap-index/`.
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

When the watched repo or workspace is missing index state, the initial warmup
scan now launches the Go `bootstrap-index` runtime before the incremental
watcher takes over.

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

---

## `pcg delete`

Removes a repository from the database. This does *not* delete your actual files, only the graph index.

**Usage:**
```bash
pcg delete [path] [options]
```

**Common Options:**

*   `--all`: Dangerous. Wipes the entire database.

---

## `pcg bundle` Commands

Tools for managing portable graph snapshots (`.pcg` files).

### `pcg bundle export`
Save your graph to a file. Useful for sharing context with team members or loading into a production read-only instance.
```bash
pcg bundle export my-graph.pcg --repo /path/to/repo
```

### `pcg bundle load`
Download and install a popular library bundle from our registry.
*(Alias: `pcg load`)*

```bash
pcg load flask
```

### `pcg bundle upload`
Upload a local `.pcg` bundle to a running PCG HTTP service. This is the
supported opt-in path when you want dependency internals on a remote instance
without indexing vendored source trees by default.

```bash
pcg bundle upload vendor-lib.pcg --service-url http://localhost:8080 --clear
```

### `pcg registry`
Search for available pre-indexed bundles in the cloud registry.
**Usage:** `pcg registry [query]`

```bash
# List top bundles
pcg registry

# Search for a specific package
pcg registry pandas
```

## Related docs

- [Bundles Guide](../guides/bundles.md)
- [Troubleshooting](troubleshooting.md)
