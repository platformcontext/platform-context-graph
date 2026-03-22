# Kotlin Parser

## Parser: `KotlinTreeSitterParser` in `src/platform_context_graph/tools/languages/kotlin.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Objects (`object`) | `classes` | Class | Supported |
| Companion objects | `classes` | Class | Supported |
| Imports | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Property declarations | `variables` | Variable | Supported |
| Class context on functions | class_context on Function | - | Supported |
| Secondary constructors | context metadata | - | Partial |

## Fixture Repo
`tests/fixtures/ecosystems/kotlin_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestKotlinGraph`

## Known Limitations
- Kotlin interfaces are not separately bucketed from classes
- Extension functions are captured as regular functions without extension receiver tracking
- Coroutine suspend functions do not carry a suspend flag in the output
