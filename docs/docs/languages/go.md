# Go Parser

## Parser: `GoTreeSitterParser` in `src/platform_context_graph/tools/languages/go.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions | `functions` | Function | Supported |
| Structs | `classes` | Class | Supported |
| Interfaces | `classes`/`interfaces` | Class/Interface | Supported |
| Imports | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Variables | `variables` | Variable | Supported |
| Methods (receivers) | `functions` with class_context | Function | Supported |
| Generics | `functions`/`classes` | Function/Class | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/go_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestGoGraph`

## Known Limitations
- Generic type constraints may not be fully captured
- Channel types not separately tracked
