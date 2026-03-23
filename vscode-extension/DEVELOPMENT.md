# Development Guide

## Quick Onboarding

```bash
cd vscode-extension
npm install
npm run compile
```

Then in VS Code:

1. Open the `vscode-extension/` directory
2. Press `F5` to launch the Extension Development Host
3. A new VS Code window opens with the extension loaded

Make changes, then `Cmd+R` / `Ctrl+R` in the host window to reload.

## Prerequisites

- Node.js 20.x or higher
- VS Code 1.85.0 or higher
- pcg CLI installed (`uv tool install platform-context-graph`)

## Project Structure

```
vscode-extension/
├── src/
│   ├── extension.ts              # Entry point, command registration
│   ├── pcgManager.ts             # CLI integration layer
│   ├── statusBarManager.ts       # Status bar UI
│   ├── providers/
│   │   ├── projectsTreeProvider.ts
│   │   ├── functionsTreeProvider.ts
│   │   ├── classesTreeProvider.ts
│   │   ├── callGraphTreeProvider.ts
│   │   ├── dependenciesTreeProvider.ts
│   │   ├── codeLensProvider.ts
│   │   └── diagnosticsProvider.ts
│   └── panels/
│       └── graphVisualizationPanel.ts  # D3.js force-directed graph
├── package.json                  # Extension manifest
├── tsconfig.json
└── .eslintrc.json
```

## Architecture

**Extension Entry Point** (`extension.ts`) — Activates the extension, registers commands, initializes providers, and sets up file watchers.

**PCG Manager** (`pcgManager.ts`) — All communication with the pcg CLI. Executes commands, parses output, and provides typed interfaces.

**Tree View Providers** (`providers/`) — Five data providers implementing `vscode.TreeDataProvider` for Projects, Functions, Classes, Call Graph, and Dependencies views.

**Code Lens Provider** — Shows inline caller/callee counts above function definitions.

**Diagnostics Provider** — Dead code and complexity warnings fed into the Problems panel.

**Graph Visualization** (`panels/graphVisualizationPanel.ts`) — Interactive D3.js force-directed graph rendered in a webview panel.

## Development Workflow

```bash
# Watch mode (auto-recompile on changes)
npm run watch

# Lint
npm run lint

# Run tests
npm test
```

## Adding a New Command

1. Register it in `extension.ts`:
   ```typescript
   context.subscriptions.push(
       vscode.commands.registerCommand('pcg.myCommand', async () => {
           // implementation
       })
   );
   ```
2. Add it to `package.json` under `contributes.commands`

## Adding a New Tree View

1. Create a provider in `src/providers/` implementing `vscode.TreeDataProvider`
2. Register it in `extension.ts`
3. Add it to `package.json` under `contributes.views`

## Building and Packaging

```bash
# Create VSIX package
npm run package

# Install locally
code --install-extension platform-context-graph-0.1.0.vsix
```

## UI Guidelines

- Use VS Code Codicons: `$(icon-name)`
- Use CSS variables for theming: `var(--vscode-editor-background)`
- Use `vscode.window.withProgress()` for long operations
- Show user-friendly errors via `vscode.window.showErrorMessage()`
