# Python Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/tools/parser_capabilities/specs/python.yaml`

## Parser Contract
- Language: `python`
- Family: `language`
- Parser: `PythonTreeSitterParser`
- Entrypoint: `src/platform_context_graph/tools/languages/python.py`
- Fixture repo: `tests/fixtures/ecosystems/python_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_python_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestPythonGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_python_parser.py::TestPythonParser::test_parse_simple_function` | `tests/integration/test_language_graph.py::TestPythonGraph::test_entity_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_python_parser.py::TestPythonParser::test_parse_class_with_method` | `tests/integration/test_language_graph.py::TestPythonGraph::test_entity_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_python_parser.py::TestPythonParser::test_parse_imports_calls_and_inheritance` | `tests/integration/test_language_graph.py::TestPythonGraph::test_import_edges_created` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_python_parser.py::TestPythonParser::test_parse_imports_calls_and_inheritance` | `tests/integration/test_language_graph.py::TestPythonGraph::test_function_call_edges_created` | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_python_parser.py::TestPythonParser::test_parse_variables_and_omits_decorator_metadata` | `tests/integration/test_language_graph.py::TestPythonGraph::test_variable_nodes_created` | - |
| Decorators | `decorators` | unsupported | `functions` | `name, line_number, decorators` | `none:not_persisted` | `tests/unit/parsers/test_python_parser.py::TestPythonParser::test_parse_variables_and_omits_decorator_metadata` | `tests/integration/test_language_graph.py::TestPythonGraph::test_decorator_metadata_not_persisted` | Decorator syntax is not emitted in the current parse result, so there is no decorator metadata to persist or query. |
| Async functions | `async-functions` | unsupported | `functions` | `name, line_number, async` | `none:not_persisted` | `tests/unit/parsers/test_python_parser.py::TestPythonParser::test_parse_async_functions_do_not_emit_async_flag` | `tests/integration/test_language_graph.py::TestPythonGraph::test_async_flag_not_persisted` | Async function definitions are parsed as ordinary function nodes without a dedicated async flag. |
| Inheritance | `inheritance` | supported | `classes` | `name, line_number, bases` | `relationship:INHERITS` | `tests/unit/parsers/test_python_parser.py::TestPythonParser::test_parse_imports_calls_and_inheritance` | `tests/integration/test_language_graph.py::TestPythonGraph::test_inheritance_edges` | - |
| Type annotations | `type-annotations` | unsupported | `type_annotations` | `name, line_number, type` | `none:not_persisted` | `tests/unit/parsers/test_python_parser.py::TestPythonParser::test_parse_does_not_emit_type_annotation_bucket` | `tests/integration/test_language_graph.py::TestPythonGraph::test_type_annotation_nodes_not_created` | The parser does not emit a dedicated `type_annotations` bucket, so annotation metadata is neither extracted nor persisted as a first-class graph surface. |

## Known Limitations
- Lambda functions detected as unnamed functions
- Comprehension-internal functions not always tracked
- Metaclass relationships not captured
