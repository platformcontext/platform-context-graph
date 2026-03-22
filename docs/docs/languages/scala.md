# Scala Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/tools/parser_capabilities/specs/scala.yaml`

## Parser Contract
- Language: `scala`
- Family: `language`
- Parser: `ScalaTreeSitterParser`
- Entrypoint: `src/platform_context_graph/tools/languages/scala.py`
- Fixture repo: `tests/fixtures/ecosystems/scala_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_scala_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestScalaGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions (`def`) | `functions-def` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_scala_parser.py::test_parse_functions` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_scala_parser.py::test_parse_classes` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Objects (`object`) | `objects-object` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_scala_parser.py::test_parse_object` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Traits | `traits` | supported | `traits` | `name, line_number` | `node:Trait` | `tests/unit/parsers/test_scala_parser.py::test_parse_traits` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_scala_parser.py::test_parse_imports` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_scala_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Generic function calls | `generic-function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_scala_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Val definitions | `val-definitions` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_scala_parser.py::test_parse_variables` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Var definitions | `var-definitions` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_scala_parser.py::test_parse_variables` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Parent context (class_context) | `parent-context-class-context` | supported | `functions` | `name, line_number, class_context` | `property:Function.class_context` | `tests/unit/parsers/test_scala_parser.py::test_parse_function_class_context` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |

## Known Limitations
- Implicit conversions and given/using clauses (Scala 3) are not separately tracked
- Pattern matching extractors are not modeled as function calls
- For-comprehension generators are not surfaced as variable bindings
