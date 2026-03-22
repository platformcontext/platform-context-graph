# C++ Parser

## Parser: `CppTreeSitterParser` in `src/platform_context_graph/tools/languages/cpp.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Functions | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Structs | `classes` (via struct_specifier) | Class | Supported |
| Enums | `classes` (via enum_specifier) | Class | Supported |
| Unions | `classes` (via union_specifier) | Class | Supported |
| Includes | `imports` | (IMPORTS edge) | Supported |
| Function calls | `function_calls` | (CALLS edge) | Supported |
| Method calls | `function_calls` | (CALLS edge) | Supported |
| Variables (initialized) | `variables` | Variable | Supported |
| Field declarations | `variables` | Variable | Supported |
| Macros (`#define`) | `classes` (macro bucket) | - | Supported |
| Lambda assignments | `functions` | Function | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/cpp_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestCppGraph`

## Known Limitations
- Template specializations are not separately modeled
- Operator overloads are captured as regular functions without operator context
- Preprocessor-conditional code blocks are parsed as-is without branch tracking
