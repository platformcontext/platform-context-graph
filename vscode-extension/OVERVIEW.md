# Extension Overview

The PlatformContextGraph VS Code extension brings graph-backed code analysis into the IDE. It wraps the pcg CLI and presents its capabilities through native VS Code UI elements.

## What it provides

- **5 tree view panels** — Projects, Functions, Classes, Call Graph, Dependencies
- **16 commands** — Indexing, search, navigation, and analysis operations
- **Code lens** — Inline caller/callee counts above function definitions
- **Diagnostics** — Dead code and complexity warnings in the Problems panel
- **Graph visualization** — Interactive D3.js force-directed call graphs in webview panels
- **9 settings** — Database path, auto-indexing, code lens toggle, complexity threshold, etc.

## How it works

The extension shells out to the pcg CLI for all graph operations. `pcgManager.ts` handles command execution and output parsing. Results are fed into VS Code's tree view, code lens, diagnostics, and webview APIs.

Auto-detection finds `pcg` in virtual environments (`.venv/bin/pcg`, `venv/bin/pcg`) or falls back to the system PATH.

## Current limitations

- Targets code-only workflows — IaC graph nodes are not yet visualized
- No Language Server Protocol (LSP) integration yet
- Graph visualization performance depends on the number of nodes (large call graphs may be slow)
- The extension does not connect to the deployed HTTP API — it only uses the local CLI

## Related docs

- [README.md](README.md) — User-facing features and settings
- [DEVELOPMENT.md](DEVELOPMENT.md) — Architecture and development setup
- [QUICKSTART.md](QUICKSTART.md) — First-run guide
- [TESTING.md](TESTING.md) — Testing procedures
