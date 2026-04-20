# Quick Start

## Before you start

Make sure you have:

- [ ] VS Code 1.85.0 or higher
- [ ] pcg CLI built and available on PATH (`cd go && go build -o bin/ ./cmd/pcg`)
- [ ] pcg is on your PATH (run `pcg --version` to verify)
- [ ] A code project to index

## Install the extension

### From VSIX (development builds)

```bash
cd vscode-extension
npm install
npm run compile
npm run package
code --install-extension platform-context-graph-0.1.0.vsix
```

Then reload VS Code: `Cmd+Shift+P` -> "Developer: Reload Window"

## First steps

### 1. Open a project

Open any code project in VS Code.

### 2. Index your code

`Cmd+Shift+P` / `Ctrl+Shift+P` -> "PCG: Index Current Workspace"

The status bar shows progress.

### 3. Explore the sidebar

Click the PCG icon in the activity bar:

- **Projects** — indexed projects with statistics
- **Functions** — functions grouped by file
- **Classes** — classes grouped by file
- **Call Graph** — callers and callees for the current function
- **Dependencies** — imports for the active file

### 4. View a call graph

Right-click a function name -> "PCG: Show Call Graph"

The interactive graph supports zoom (mouse wheel), pan (drag), and node repositioning.

### 5. Use code lens

With code lens enabled, you'll see inline info above function definitions:

```
← 3 callers | → 5 callees | Show Call Graph
def process_data(data):
    ...
```

Click any label to navigate or visualize.

## Common tasks

| Task | How |
| :--- | :--- |
| Search code | `Cmd+Shift+P` -> "PCG: Search Code" |
| Find dead code | `Cmd+Shift+P` -> "PCG: Find Dead Code" |
| Analyze complexity | `Cmd+Shift+P` -> "PCG: Analyze Complexity" |
| Load a bundle | `Cmd+Shift+P` -> "PCG: Load Bundle" |
| Re-index | `Cmd+Shift+P` -> "PCG: Re-index Current Workspace" |

## Troubleshooting

If `pcg` is not found, either install it globally or set `pcg.cliPath` in VS Code settings to the full path.

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for more.
