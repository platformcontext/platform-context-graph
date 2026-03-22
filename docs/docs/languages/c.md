# C Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/tools/parser_capabilities/specs/c.yaml`

## Parser Contract
- Language: `c`
- Family: `language`
- Parser: `CTreeSitterParser`
- Entrypoint: `src/platform_context_graph/tools/languages/c.py`
- Fixture repo: `tests/fixtures/ecosystems/c_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_c_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestCGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_c_parser.py::test_parse_functions` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Pointer-returning functions | `pointer-returning-functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_c_parser.py::test_parse_functions` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Structs | `structs` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_c_parser.py::test_parse_structs` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Unions | `unions` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_c_parser.py::test_parse_unions` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_c_parser.py::test_parse_enums` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Typedefs | `typedefs` | unsupported | `typedefs` | `name, line_number` | `none:not_persisted` | `tests/unit/parsers/test_c_parser.py::test_parse_typedefs_do_not_emit_dedicated_entities` | `tests/integration/test_language_graph.py::TestCGraph::test_typedef_nodes_not_created` | Typedef syntax is tolerated during parsing, but the normalized parser output does not emit dedicated typedef entities and the graph layer has no Typedef node surface. |
| Includes | `includes` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_c_parser.py::test_parse_includes` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_c_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Variables (initialized declarations) | `variables-initialized-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_c_parser.py::test_parse_initialized_variables` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Macros (`#define`) | `macros-define` | supported | `macros` | `name, line_number` | `node:Macro` | `tests/unit/parsers/test_c_parser.py::test_parse_macros` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |

## Known Limitations
- Function pointer declarations are not modeled as callable entities
- Preprocessor macros with complex expansions are captured by name only
- Variadic functions do not expose their variadic argument types
