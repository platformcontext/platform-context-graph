# JavaScript Parser

## Parser: `JavascriptTreeSitterParser` in `src/platform_context_graph/tools/languages/javascript.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Function declarations | `functions` | Function | Supported |
| Function expressions | `functions` | Function | Supported |
| Arrow functions (named) | `functions` | Function | Supported |
| Method definitions | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Imports (`import`/`require`) | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Member call expressions | `function_calls` | (CALLS edge) | Supported |
| Variables | `variables` | Variable | Supported |
| JSDoc comments | jsdoc property on Function | - | Supported |
| Method kind (get/set/async) | js_kind on Function | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/javascript_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestJavaScriptGraph`

## Known Limitations
- Computed property names in classes are not resolved to static names
- Dynamic `require()` calls with non-literal paths are not tracked
- Generator functions are captured as regular functions without generator flag
