# Haskell Parser

## Parser: `HaskellTreeSitterParser` in `src/platform_context_graph/tools/languages/haskell.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Function declarations | `functions` | Function | Supported |
| Initializer declarations | `functions` | Function | Supported |
| Type classes | `classes` | Class | Supported |
| Data types (struct-like) | `classes` | Class | Supported |
| Enumerations | `classes` | Class | Supported |
| Protocols/typeclasses | `classes` | Interface | Supported |
| Import declarations | `imports` | (IMPORTS edge) | Supported |
| Function call expressions | `function_calls` | (CALLS edge) | Supported |
| Property/binding declarations | `variables` | Variable | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/haskell_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestHaskellGraph`

## Known Limitations
- Type class instances are not modeled as inheritance relationships
- Where-clauses and let-bindings define local names that are not separately graphed
- Point-free style definitions may result in functions with no parameter information
