# PlatformContextGraph VS Code Extension

AI-powered code analysis with graph database integration, directly in your IDE.

## Features

### 🔍 **Intelligent Code Navigation**
- **Search**: Quickly find functions, classes, and files across your codebase
- **Go to Definition**: Navigate to any code element with a single click
- **Call Graph**: Visualize function call relationships with interactive graphs

### 📊 **Code Analysis**
- **Call Analysis**: See who calls what, and trace execution flows
- **Complexity Analysis**: Identify complex functions that need refactoring
- **Dead Code Detection**: Find unused functions and classes
- **Dependency Tracking**: Understand file dependencies and imports

### 🌳 **Tree Views**
- **Projects**: Browse all indexed projects
- **Functions**: Explore functions grouped by file
- **Classes**: Navigate class hierarchies
- **Call Graph**: Interactive caller/callee exploration
- **Dependencies**: View file dependencies in real-time

### 💡 **Code Lens**
- Inline caller/callee counts above function definitions
- Quick access to call graph visualization
- One-click navigation to related code

### ⚠️ **Diagnostics**
- Real-time warnings for dead code
- Complexity warnings for functions exceeding thresholds
- Integrated with VS Code's Problems panel

### 📦 **Bundle Support**
- Load pre-indexed bundles for popular libraries (numpy, pandas, etc.)
- Instant code understanding without indexing

## Requirements

- **pcg CLI**: Install the PlatformContextGraph CLI
  ```bash
  pip install platform-context-graph
  ```
- **VS Code**: Version 1.85.0 or higher

### 🐍 Virtual Environment Support

The extension **automatically detects** `pcg` from Python virtual environments! Just install `pcg` in your project's virtual environment (`.venv`, `venv`, etc.) and the extension will find it.

**Quick setup:**
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or .venv\Scripts\activate on Windows

# Install pcg
pip install platform-context-graph

# Open in VS Code - extension auto-detects pcg!
code .
```

For detailed setup instructions, see [VENV_SETUP.md](VENV_SETUP.md).

## Extension Settings

This extension contributes the following settings:

* `pcg.databasePath`: Path to the PCG database (default: `~/.pcg/db`)
* `pcg.autoIndex`: Automatically index workspace on startup (default: `true`)
* `pcg.indexSource`: Index full source code for search (default: `false`)
* `pcg.maxDepth`: Maximum depth for call graph traversal (default: `3`)
* `pcg.cliPath`: Path to pcg CLI executable (default: `pcg`)
* `pcg.enableCodeLens`: Show code lens for callers/callees (default: `true`)
* `pcg.enableDiagnostics`: Show diagnostics for dead code (default: `true`)
* `pcg.complexityThreshold`: Complexity threshold for warnings (default: `10`)
* `pcg.databaseType`: Database backend - `falkordb` or `neo4j` (default: `falkordb`)

## Commands

### Indexing
- `PCG: Index Current Workspace` - Index the current workspace
- `PCG: Re-index Current Workspace` - Force re-index
- `PCG: Load Bundle` - Load a pre-indexed bundle

### Navigation
- `PCG: Search Code` - Search for functions, classes, files
- `PCG: Show Call Graph` - Visualize call graph for a function
- `PCG: Show Callers` - List all callers of a function
- `PCG: Show Callees` - List all callees of a function
- `PCG: Find Dependencies` - Show file dependencies

### Analysis
- `PCG: Analyze Calls` - Analyze all function calls
- `PCG: Analyze Complexity` - Find complex functions
- `PCG: Find Dead Code` - Detect unused code
- `PCG: Show Statistics` - Display project statistics
- `PCG: Show Inheritance Tree` - Visualize class inheritance

### Settings
- `PCG: Open Settings` - Open extension settings

## Usage

### Quick Start

1. **Install the extension** from the VS Code marketplace
2. **Install pcg CLI**: `pip install platform-context-graph`
3. **Open a workspace** in VS Code
4. **Index your code**: Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux), then type "PCG: Index Current Workspace"

### Exploring Code

- **Browse Projects**: Click the PCG icon in the Activity Bar
- **Search**: Use `PCG: Search Code` to find any code element
- **View Call Graph**: Right-click on a function and select "PCG: Show Call Graph"
- **Check Dependencies**: Open a file and view the Dependencies panel

### Code Lens

When enabled, you'll see inline information above function definitions:
```python
← 3 callers | → 5 callees | Show Call Graph
def process_data(data):
    ...
```

Click on any code lens to navigate or visualize.

### Interactive Graph Visualization

The call graph visualization is fully interactive:
- **Zoom**: Mouse wheel or pinch gesture
- **Pan**: Click and drag on empty space
- **Move nodes**: Drag individual nodes
- **Hover**: See detailed information
- **Controls**: Use Reset Zoom and Center buttons

## Known Issues

- Large codebases (>10,000 files) may take time to index
- Code lens may be slow on very large files
- Graph visualization performance depends on graph size

## Release Notes

### 0.1.0

Initial release of PlatformContextGraph VS Code Extension

**Features:**
- Complete PCG integration
- Tree views for projects, functions, classes, call graphs, and dependencies
- Interactive graph visualization with D3.js
- Code lens for caller/callee information
- Diagnostics for dead code and complexity
- Bundle loading support
- Comprehensive command palette integration

## Contributing

Found a bug or have a feature request? Please open an issue on [GitHub](https://github.com/platformcontext/platform-context-graph/issues).

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Enjoy using PlatformContextGraph!** 🚀
