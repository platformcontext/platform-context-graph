# Windows Setup

Windows users have two practical paths:

## Recommended: WSL

Use WSL when you want the smoothest local development workflow.

Typical flow:

1. install WSL
2. open an Ubuntu shell
3. install Python and your preferred package manager
4. install PCG
5. index from the WSL-visible project path

This keeps PCG close to the Linux/macOS experience and avoids backend limitations on native Windows.

## Alternative: native Windows + Neo4j

If you do not want WSL, use **Neo4j** as the backend and run PCG against that external database.

Recommended checklist:

1. install Python
2. install PCG
3. ensure Neo4j is reachable
4. run `pcg neo4j setup`
5. verify with `pcg doctor`

## First commands

```powershell
pcg doctor
pcg index .
pcg mcp setup
```

If path or shell behavior differs in your environment, prefer a Python virtual environment or `uv tool install` so the `pcg` command resolves cleanly.

---

## Common Windows Issues

### `'pcg' command not found`

* Restart your terminal after installation
* Ensure Python Scripts directory is in PATH
* Try: `uv tool install platform-context-graph` or `pip install platform-context-graph`

### WSL path confusion

Windows drives can be accessed from WSL using:

```bash
cd /mnt/c/
```

### Neo4j connection issues

* Ensure Neo4j is running
* Check URI format: `bolt://localhost:7687`
* Double-check username/password

---

## Verify Installation

Run:

```bash
pcg list
```
If no errors are shown, setup is complete.
