# TypeScript Parser

## Parser: `TypescriptTreeSitterParser` in `src/platform_context_graph/tools/languages/typescript.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Interfaces | `interfaces` | Interface | Supported |
| Imports | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Variables | `variables` | Variable | Supported |
| Enums | `enums` | Enum | Supported |
| Type aliases | `type_aliases` | TypeAlias | Partial |
| Decorators | decorator property | - | Supported |
| Generics | type parameters | - | Partial |

## Fixture Repo
`tests/fixtures/ecosystems/typescript_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestTypeScriptGraph`

## Known Limitations
- Type aliases are parsed (`type_aliases` key) but not persisted to the graph — no persistence mapping exists
- Mapped types and conditional types not fully captured
- Namespace declarations may be incomplete
- Declaration merging not tracked
