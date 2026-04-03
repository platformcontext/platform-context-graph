# Go Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/go.yaml`

## Parser Contract
- Language: `go`
- Family: `language`
- Parser: `GoTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/go.py`
- Fixture repo: `tests/fixtures/ecosystems/go_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_go_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestGoGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_go_parser.py::test_parse_functions` | `tests/integration/test_language_graph.py::TestGoGraph::test_runtime_surface` | - |
| Structs | `structs` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_go_parser.py::test_parse_structs` | `tests/integration/test_language_graph.py::TestGoGraph::test_runtime_surface` | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `tests/unit/parsers/test_go_parser.py::test_parse_interfaces` | `tests/integration/test_language_graph.py::TestGoGraph::test_runtime_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_go_parser.py::test_parse_imports` | `tests/integration/test_language_graph.py::TestGoGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_go_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestGoGraph::test_runtime_surface` | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_go_parser.py::test_parse_package_vars` | `tests/integration/test_language_graph.py::TestGoGraph::test_runtime_surface` | - |
| Methods (receivers) | `methods-receivers` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_go_parser.py::test_parse_methods` | `tests/integration/test_language_graph.py::TestGoGraph::test_runtime_surface` | - |
| Generics | `generics` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_go_parser.py::test_parse_generics` | `tests/integration/test_language_graph.py::TestGoGraph::test_runtime_surface` | - |

## Known Limitations
- Generic type constraints may not be fully captured
- Channel types not separately tracked
