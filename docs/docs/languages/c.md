# C Parser

## Parser: `CTreeSitterParser` in `src/platform_context_graph/tools/languages/c.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions | `functions` | Function | Supported |
| Pointer-returning functions | `functions` | Function | Supported |
| Structs | `classes` (structs bucket) | Class | Supported |
| Unions | `classes` (unions bucket) | Class | Supported |
| Enums | `classes` (enums bucket) | Class | Supported |
| Typedefs | `classes` (typedefs bucket) | - | Supported |
| Includes | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Variables (initialized declarations) | `variables` | Variable | Supported |
| Macros (`#define`) | `classes` (macros bucket) | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/c_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestCGraph`

## Known Limitations
- Function pointer declarations are not modeled as callable entities
- Preprocessor macros with complex expansions are captured by name only
- Variadic functions do not expose their variadic argument types
