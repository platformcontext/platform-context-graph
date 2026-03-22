# PHP Parser

## Parser: `PhpTreeSitterParser` in `src/platform_context_graph/tools/languages/php.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions | `functions` | Function | Supported |
| Methods | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Interfaces | `classes` (interfaces bucket) | Interface | Supported |
| Traits | `classes` (traits bucket) | Trait | Supported |
| Use declarations | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Member method calls | `function_calls` | (CALLS edge) | Supported |
| Static method calls | `function_calls` | (CALLS edge) | Supported |
| Object creation (`new`) | `function_calls` | (CALLS edge) | Supported |
| Variables | `variables` | Variable | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/php_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestPhpGraph`

## Known Limitations
- Trait `use` inside class bodies is not linked as an INHERITS relationship
- Anonymous classes are not modeled as distinct nodes
- Magic methods (`__get`, `__call`) are captured as regular methods without special classification
