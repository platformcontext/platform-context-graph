# TypeScript JSX Parser

## Parser: `TypescriptJSXTreeSitterParser` in `src/platform_context_graph/tools/languages/typescriptjsx.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Interfaces | `interfaces` | Interface | Supported |
| Imports | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Variables | `variables` | Variable | Supported |
| Type aliases | `type_aliases` | TypeAlias | Partial |
| JSX component usage | `function_calls` | (CALLS edge) | Partial |

## Fixture Repo
`tests/fixtures/ecosystems/tsx_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py` (uses TypeScript test infrastructure)

## Known Limitations
- JSX element tag names are not modeled as distinct component reference nodes
- Fragment shorthand (`<>...</>`) is not separately tracked
- TSX-specific type narrowing patterns (e.g., `as ComponentType`) are not captured
