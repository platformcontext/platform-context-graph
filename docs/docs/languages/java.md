# Java Parser

## Parser: `JavaTreeSitterParser` in `src/platform_context_graph/tools/languages/java.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Methods | `functions` | Function | Supported |
| Constructors | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Interfaces | `classes` | Class | Supported |
| Enums | `classes` | Class | Supported |
| Annotation types | `classes` | Class | Supported |
| Imports | `imports` | (IMPORTS edge) | Supported |
| Method invocations | `function_calls` | (CALLS edge) | Supported |
| Object creation | `function_calls` | (CALLS edge) | Supported |
| Local variables | `variables` | Variable | Supported |
| Field declarations | `variables` | Variable | Supported |
| Annotations (applied) | annotation properties | - | Partial |

## Fixture Repo
`tests/fixtures/ecosystems/java_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestJavaGraph`

## Known Limitations
- Generic type bounds and wildcards not captured as structured data
- Anonymous inner classes not separately tracked
- Lambda expressions not individually modeled as functions
