# Troubleshooting

## Decision tree

```
Extension not working?
├── PCG icon missing from activity bar?
│   └── Extension not installed or not activated → reinstall and reload
├── Commands fail with "pcg not found"?
│   ├── Is pcg on PATH? → run `pcg --version` in terminal
│   ├── Using a virtual environment? → extension auto-detects .venv/bin/pcg
│   └── Neither works? → set pcg.cliPath manually in settings
├── Indexing fails?
│   ├── Does `pcg index .` work from terminal? → extension issue
│   └── CLI also fails? → pcg or database issue, not extension
├── Tree views empty?
│   └── Workspace not indexed → run "PCG: Index Current Workspace"
├── Call graph blank?
│   ├── Check Output panel for errors
│   └── Try a function with known callers
├── Code lens not showing?
│   ├── Check pcg.enableCodeLens is true
│   └── Reload window
└── Diagnostics not appearing?
    ├── Check pcg.enableDiagnostics is true
    └── Save the file to trigger diagnostics
```

## "pcg: command not found"

The extension searches for `pcg` in this order:

1. Virtual environment in the workspace (`.venv/bin/pcg`, `venv/bin/pcg`)
2. System PATH
3. `pcg.cliPath` setting (if set)

Fix:

```bash
# Verify pcg is installed
uv tool install platform-context-graph
pcg --version
```

If pcg is installed but the extension can't find it, set the path manually:

Settings -> search "pcg.cliPath" -> set to the full path (e.g., `/Users/you/.local/bin/pcg`)

## Indexing fails

Test the CLI directly:

```bash
pcg index .
pcg list
```

If the CLI works but the extension doesn't, check the Output panel (View -> Output -> "PlatformContextGraph") for the exact error.

## Graph visualization not rendering

1. Open Developer Tools: Help -> Toggle Developer Tools
2. Check the Console tab for JavaScript errors
3. Try a function with fewer connections (large graphs may time out)

## Extension not activating

```bash
# Check if installed
code --list-extensions | grep platformcontext

# Reinstall
code --uninstall-extension platformcontext.platform-context-graph
code --install-extension platform-context-graph-0.1.0.vsix
```

Then reload: `Cmd+Shift+P` -> "Developer: Reload Window"

## Checking logs

Three log sources, in order of usefulness:

1. **Extension logs:** View -> Output -> "PlatformContextGraph"
2. **Extension host:** View -> Output -> "Log (Extension Host)"
3. **Developer tools:** Help -> Toggle Developer Tools -> Console

## Still stuck?

Open an issue on [GitHub](https://github.com/platformcontext/platform-context-graph/issues) with:

- `pcg --version` output
- VS Code version (`code --version`)
- The full error from the Output panel
