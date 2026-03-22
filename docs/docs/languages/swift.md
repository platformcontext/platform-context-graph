# Swift Parser

## Parser: `SwiftTreeSitterParser` in `src/platform_context_graph/tools/languages/swift.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions | `functions` | Function | Supported |
| Initializers (`init`) | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Structs | `classes` (struct kind) | Class | Supported |
| Enums | `classes` (enum kind) | Class | Supported |
| Protocols | `classes` (protocol kind) | Interface | Supported |
| Actors | `classes` | Class | Supported |
| Imports | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Property declarations | `variables` | Variable | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/swift_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestSwiftGraph`

## Known Limitations
- Property wrappers are not tracked as distinct decorators
- `@objc` and dynamic dispatch attributes are not modeled in the graph
- Computed property bodies are not traversed for embedded function calls
