# JavaScript Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/tools/parser_capabilities/specs/javascript.yaml`

## Parser Contract
- Language: `javascript`
- Family: `language`
- Parser: `JavascriptTreeSitterParser`
- Entrypoint: `src/platform_context_graph/tools/languages/javascript.py`
- Fixture repo: `tests/fixtures/ecosystems/javascript_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_javascript_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestJavaScriptGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Function declarations | `function-declarations` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_javascript_parser.py::test_parse_javascript_simple_declarations` | `tests/integration/test_language_graph.py::TestJavaScriptGraph::test_runtime_surface` | - |
| Function expressions | `function-expressions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_javascript_parser.py::test_parse_javascript_runtime_surface` | `tests/integration/test_language_graph.py::TestJavaScriptGraph::test_runtime_surface` | - |
| Arrow functions (named) | `arrow-functions-named` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_javascript_parser.py::test_parse_javascript_runtime_surface` | `tests/integration/test_language_graph.py::TestJavaScriptGraph::test_runtime_surface` | - |
| Method definitions | `method-definitions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_javascript_parser.py::test_parse_javascript_runtime_surface` | `tests/integration/test_language_graph.py::TestJavaScriptGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_javascript_parser.py::test_parse_javascript_runtime_surface` | `tests/integration/test_language_graph.py::TestJavaScriptGraph::test_runtime_surface` | - |
| Imports (`import`/`require`) | `imports-import-require` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_javascript_parser.py::test_parse_javascript_runtime_surface` | `tests/integration/test_language_graph.py::TestJavaScriptGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_javascript_parser.py::test_parse_javascript_runtime_surface` | `tests/integration/test_language_graph.py::TestJavaScriptGraph::test_runtime_surface` | - |
| Member call expressions | `member-call-expressions` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_javascript_parser.py::test_parse_javascript_runtime_surface` | `tests/integration/test_language_graph.py::TestJavaScriptGraph::test_runtime_surface` | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_javascript_parser.py::test_parse_javascript_runtime_surface` | `tests/integration/test_language_graph.py::TestJavaScriptGraph::test_runtime_surface` | - |
| JSDoc comments | `jsdoc-comments` | unsupported | `functions` | `name, line_number, docstring` | `none:not_persisted` | `tests/unit/parsers/test_javascript_parser.py::test_parse_javascript_runtime_surface` | `tests/integration/test_language_graph.py::TestJavaScriptGraph::test_jsdoc_metadata_not_persisted` | The parser leaves JavaScript `docstring` fields empty, so JSDoc comments are not extracted or persisted as graph metadata. |
| Method kind (get/set/async) | `method-kind-get-set-async` | partial | `functions` | `name, line_number, type` | `property:Function.type` | `tests/unit/parsers/test_javascript_parser.py::test_parse_javascript_runtime_surface` | `tests/integration/test_language_graph.py::TestJavaScriptGraph::test_getter_metadata_persisted` | Getter methods are emitted with `type='getter'`, but setter and async metadata are not captured consistently enough to claim full support. |

## Known Limitations
- Computed property names in classes are not resolved to static names
- Dynamic `require()` calls with non-literal paths are not tracked
- Generator functions are captured as regular functions without generator flag
