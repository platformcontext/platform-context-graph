# CLI: System & Configuration

Commands to manage the PlatformContextGraph engine itself.

## `pcg doctor`

Self-diagnostic tool. Runs a health check on your installation.

**Checks performed:**

*   Database connectivity (Neo4j / FalkorDB).
*   Python version compatibility.
*   Required dependencies.

**Usage:**
```bash
pcg doctor
```

---

## `pcg mcp setup`

The interactive wizard for configuring AI clients.

**What it does:**

1.  Detects installed AI Clients (Cursor, VS Code, Claude).
2.  Creates the necessary config files (e.g., `mcp.json`).
3.  Generates a `.env` file with database credentials.

**Usage:**
```bash
pcg mcp setup
```

---

## `pcg neo4j setup`

The interactive wizard for configuring the graph database backend.

**What it does:**

*   **Docker:** Pulls and runs the official Neo4j image.
*   **Local:** Helps locate a local installation.
*   **Remote:** Configures credentials for AuraDB.

**Usage:**
```bash
pcg neo4j setup
```

---

## `pcg config` Commands

Directly modify settings without editing text files.

*   `pcg config show`: Print current configuration.
*   `pcg config set <key> <value>`: Update a setting.
    *   Example: `pcg config set DEFAULT_DATABASE neo4j`
*   `pcg config db <backend>`: Switch backends (shortcut).
    *   Example: `pcg config db falkordb`
