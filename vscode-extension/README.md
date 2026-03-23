# PlatformContextGraph VS Code Extension

Code analysis with graph database integration, directly in VS Code.

## Features

**Code Navigation** — Search for functions, classes, and files. Go to definition from tree views. Visualize call graphs interactively.

**Code Analysis** — Call graph analysis, cyclomatic complexity detection, dead code finder, and dependency tracking. Results feed into tree views, code lens, and the Problems panel.

**Tree Views** — Five panels in the activity bar: Projects, Functions, Classes, Call Graph, and Dependencies. Click any item to navigate.

**Code Lens** — Inline caller/callee counts above function definitions with one-click navigation.

**Diagnostics** — Dead code and complexity warnings integrated with VS Code's Problems panel.

**Bundles** — Load pre-indexed library graphs (numpy, pandas, etc.) without re-indexing.

## Requirements

- VS Code 1.85.0 or higher
- pcg CLI installed:
  ```bash
  uv tool install platform-context-graph
  ```

The extension auto-detects `pcg` from virtual environments (`.venv`, `venv`). If auto-detection fails, set the path manually via `pcg.cliPath` in settings.

## Quick Start

1. Install the extension
2. Open a workspace in VS Code
3. `Cmd+Shift+P` / `Ctrl+Shift+P` -> "PCG: Index Current Workspace"
4. Click the PCG icon in the activity bar to explore

## Commands

**Indexing:** Index Current Workspace, Re-index Current Workspace, Load Bundle

**Navigation:** Search Code, Show Call Graph, Show Callers, Show Callees, Find Dependencies

**Analysis:** Analyze Calls, Analyze Complexity, Find Dead Code, Show Statistics, Show Inheritance Tree

**Settings:** Open Settings

## Settings

| Setting | Default | Description |
| :--- | :--- | :--- |
| `pcg.databasePath` | `~/.pcg/db` | Path to the PCG database |
| `pcg.autoIndex` | `true` | Index workspace on startup |
| `pcg.indexSource` | `false` | Index full source code for search |
| `pcg.maxDepth` | `3` | Max call graph traversal depth |
| `pcg.cliPath` | `pcg` | Path to pcg CLI executable |
| `pcg.enableCodeLens` | `true` | Show inline caller/callee counts |
| `pcg.enableDiagnostics` | `true` | Show dead code and complexity warnings |
| `pcg.complexityThreshold` | `10` | Complexity threshold for warnings |
| `pcg.databaseType` | `falkordb` | Database backend (`falkordb` or `neo4j`) |

## Known Limitations

- Large codebases (>10,000 files) may take time to index
- Code lens can be slow on very large files
- Graph visualization performance depends on graph size
- The extension currently targets code-only workflows (no IaC graph visualization yet)

## Contributing

Found a bug or have a feature request? Open an issue on [GitHub](https://github.com/platformcontext/platform-context-graph/issues).

## License

MIT License — see [LICENSE](LICENSE) for details.
