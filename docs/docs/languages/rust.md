# Rust Parser

## Parser: `RustTreeSitterParser` in `src/platform_context_graph/tools/languages/rust.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions | `functions` | Function | Supported |
| Structs | `classes` | Class | Supported |
| Enums | `classes` | Class | Supported |
| Traits | `traits` | Trait | Supported |
| Imports | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Method calls (field expressions) | `function_calls` | (CALLS edge) | Supported |
| Scoped calls (path::fn) | `function_calls` | (CALLS edge) | Supported |
| Impl blocks | context on Function | - | Partial |

## Fixture Repo
`tests/fixtures/ecosystems/rust_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestRustGraph`

## Known Limitations
- `impl Trait for Type` implementations are not tracked as distinct graph edges
- Lifetime annotations are not captured
- Macro-generated code is not traversed
