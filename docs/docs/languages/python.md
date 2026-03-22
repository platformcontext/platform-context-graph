# Python Parser

## Parser: `PythonTreeSitterParser` in `src/platform_context_graph/tools/languages/python.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Imports | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Variables | `variables` | Variable | Supported |
| Decorators | decorator property on Function | - | Supported |
| Async functions | `functions` (async flag) | Function | Supported |
| Inheritance | `classes[].bases` | (INHERITS edge) | Supported |
| Type annotations | type properties | - | Partial |

## Fixture Repo
`tests/fixtures/ecosystems/python_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestPythonGraph`

## Known Limitations
- Lambda functions detected as unnamed functions
- Comprehension-internal functions not always tracked
- Metaclass relationships not captured
