# Scala Parser

## Parser: `ScalaTreeSitterParser` in `src/platform_context_graph/tools/languages/scala.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions (`def`) | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Objects (`object`) | `classes` | Class | Supported |
| Traits | `traits` | Trait | Supported |
| Imports | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Generic function calls | `function_calls` | (CALLS edge) | Supported |
| Val definitions | `variables` | Variable | Supported |
| Var definitions | `variables` | Variable | Supported |
| Parent context (class_context) | context on Function | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/scala_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestScalaGraph`

## Known Limitations
- Implicit conversions and given/using clauses (Scala 3) are not separately tracked
- Pattern matching extractors are not modeled as function calls
- For-comprehension generators are not surfaced as variable bindings
