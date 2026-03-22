# Elixir Parser

## Parser: `ElixirTreeSitterParser` in `src/platform_context_graph/tools/languages/elixir.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions (`def`/`defp`) | `functions` | Function | Supported |
| Macros (`defmacro`/`defmacrop`) | `functions` | Function | Supported |
| Guards (`defguard`/`defguardp`) | `functions` | Function | Supported |
| Delegated functions (`defdelegate`) | `functions` | Function | Supported |
| Modules (`defmodule`) | `classes` | Class | Supported |
| Protocols (`defprotocol`) | `classes` | Class | Supported |
| Protocol implementations (`defimpl`) | `classes` | Class | Supported |
| Use/import/alias/require | `imports` | (IMPORTS edge) | Supported |
| Dot-notation calls | `function_calls` | (CALLS edge) | Supported |
| Simple function calls | `function_calls` | (CALLS edge) | Supported |
| Module attributes (`@attr`) | module_attributes metadata | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/elixir_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestElixirGraph`

## Known Limitations
- Multiple function clause heads for the same function are each captured as separate entries
- Pipe operator (`|>`) chains are not collapsed into a single call chain node
- GenServer callbacks are not distinguished from regular function definitions
