# Testing

## Quick smoke test

The fastest way to verify the extension works:

1. Open VS Code with the extension installed
2. `Cmd+Shift+P` -> "PCG: Index Current Workspace"
3. Confirm the Projects tree view populates
4. Right-click a function -> "PCG: Show Call Graph"
5. Confirm the graph renders

If all five steps pass, the extension is functional.

## Prerequisites

- Node.js 20.x or higher
- VS Code 1.85.0 or higher
- pcg CLI installed and on PATH

## Installing for testing

```bash
cd vscode-extension
npm install
npm run compile
npm run package
code --install-extension platform-context-graph-0.1.0.vsix
```

## Full test checklist

### Installation

- [ ] Extension installs without errors
- [ ] PCG icon appears in the activity bar
- [ ] Extension activates (check Output -> "PlatformContextGraph")

### Indexing

- [ ] "PCG: Index Current Workspace" completes
- [ ] "PCG: Re-index Current Workspace" forces a fresh index
- [ ] Status bar shows indexing progress

### Tree views

- [ ] Projects panel shows indexed project with stats
- [ ] Functions panel shows functions grouped by file
- [ ] Classes panel shows classes grouped by file
- [ ] Call Graph panel updates for the current function
- [ ] Dependencies panel shows imports for the active file
- [ ] Clicking any item navigates to its definition

### Search and navigation

- [ ] "PCG: Search Code" finds functions and classes
- [ ] Selecting a result navigates to the correct file and line

### Call graph

- [ ] "PCG: Show Call Graph" opens an interactive webview
- [ ] Zoom, pan, and node drag work
- [ ] Hover shows tooltips

### Code lens

- [ ] Caller/callee counts appear above function definitions
- [ ] Clicking a count navigates correctly
- [ ] "Show Call Graph" link opens the visualization

### Diagnostics

- [ ] Dead code warnings appear in the Problems panel
- [ ] Complexity warnings appear for high-complexity functions
- [ ] Warnings update on file save

### Analysis commands

- [ ] "PCG: Find Dead Code" returns results
- [ ] "PCG: Analyze Complexity" returns results
- [ ] "PCG: Show Statistics" displays project stats

## Performance expectations

| Codebase size | Indexing | Search | Call graph |
| :--- | :--- | :--- | :--- |
| < 100 files | < 10s | < 1s | < 2s |
| 100–1000 files | 10–60s | 1–3s | 2–5s |
| > 1000 files | 1–5min | 3–10s | 5–15s |

## Running automated tests

```bash
npm run lint
npm test
```

## Debugging

- **Extension logs:** View -> Output -> "PlatformContextGraph"
- **Extension host errors:** View -> Output -> "Log (Extension Host)"
- **Webview debugging:** Help -> Toggle Developer Tools
