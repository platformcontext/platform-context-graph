# Ruby Parser

## Parser: `RubyTreeSitterParser` in `src/platform_context_graph/tools/languages/ruby.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Methods (`def`) | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Modules | `classes` (modules bucket) | Class | Supported |
| Require/load imports | `imports` | (IMPORTS edge) | Supported |
| Method calls | `function_calls` | (CALLS edge) | Supported |
| Instance variable assignments | `variables` | Variable | Supported |
| Local variable assignments | `variables` | Variable | Supported |
| Module inclusions (`include`/`extend`) | module_includes metadata | - | Supported |
| Parent context (class/module) | class_context on Function | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/ruby_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestRubyGraph`

## Known Limitations
- Singleton methods (defined on specific objects) are not separated from instance methods
- `method_missing` based dynamic dispatch is not tracked
- DSL-style method definitions (e.g., ActiveRecord scopes) are captured as regular calls only
