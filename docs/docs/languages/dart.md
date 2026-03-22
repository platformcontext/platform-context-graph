# Dart Parser

## Parser: `DartTreeSitterParser` in `src/platform_context_graph/tools/languages/dart.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions | `functions` | Function | Supported |
| Constructors | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Mixins | `classes` | Class | Supported |
| Extensions | `classes` | Class | Supported |
| Enums | `classes` | Class | Supported |
| Library imports | `imports` | (IMPORTS edge) | Supported |
| Library exports | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Local variable declarations | `variables` | Variable | Supported |
| Top-level variable declarations | `variables` | Variable | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/dart_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestDartGraph`

## Known Limitations
- Named constructors (`ClassName.named(...)`) are captured under the constructor name only
- Cascade notation (`..method()`) is not tracked as a distinct call chain
- `part`/`part of` directives are not modeled as import relationships
