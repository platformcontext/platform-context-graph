# C++ Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/cpp.yaml`

## Parser Contract
- Language: `cpp`
- Family: `language`
- Parser: `CppTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/cpp.py`
- Fixture repo: `tests/fixtures/ecosystems/cpp_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_cpp_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestCppGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_cpp_parser.py::test_parse_functions` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_cpp_parser.py::test_parse_classes` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |
| Structs | `structs` | supported | `structs` | `name, line_number` | `node:Struct` | `tests/unit/parsers/test_cpp_parser.py::test_parse_structs` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `enums` | `name, line_number` | `node:Enum` | `tests/unit/parsers/test_cpp_parser.py::test_parse_enums` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |
| Unions | `unions` | supported | `unions` | `name, line_number` | `node:Union` | `tests/unit/parsers/test_cpp_parser.py::test_parse_unions` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |
| Includes | `includes` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_cpp_parser.py::test_parse_includes` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_cpp_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |
| Method calls | `method-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_cpp_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |
| Variables (initialized) | `variables-initialized` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_cpp_parser.py::test_parse_variables_and_fields` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |
| Field declarations | `field-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_cpp_parser.py::test_parse_variables_and_fields` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |
| Macros (`#define`) | `macros-define` | supported | `macros` | `name, line_number` | `node:Macro` | `tests/unit/parsers/test_cpp_parser.py::test_parse_macros` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |
| Lambda assignments | `lambda-assignments` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_cpp_parser.py::test_parse_lambdas` | `tests/integration/test_language_graph.py::TestCppGraph::test_runtime_surface` | - |

## Known Limitations
- Template specializations are not separately modeled
- Operator overloads are captured as regular functions without operator context
- Preprocessor-conditional code blocks are parsed as-is without branch tracking
