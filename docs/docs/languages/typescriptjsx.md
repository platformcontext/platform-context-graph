# TypeScript JSX Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/tools/parser_capabilities/specs/typescriptjsx.yaml`

## Parser Contract
- Language: `typescriptjsx`
- Family: `language`
- Parser: `TypescriptJSXTreeSitterParser`
- Entrypoint: `src/platform_context_graph/tools/languages/typescriptjsx.py`
- Fixture repo: `tests/fixtures/ecosystems/tsx_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_typescriptjsx_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_typescriptjsx_parser.py::test_parse_tsx_components_and_interfaces` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_function_entities_created` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_typescriptjsx_parser.py::test_parse_tsx_class_components` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_class_entities_created` | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `tests/unit/parsers/test_typescriptjsx_parser.py::test_parse_tsx_components_and_interfaces` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_interface_entities_created` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_typescriptjsx_parser.py::test_parse_tsx_imports_calls_variables_and_type_aliases` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_import_edges_created` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_typescriptjsx_parser.py::test_parse_tsx_imports_calls_variables_and_type_aliases` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_call_edges_created` | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_typescriptjsx_parser.py::test_parse_tsx_imports_calls_variables_and_type_aliases` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_variable_nodes_created` | - |
| Type aliases | `type-aliases` | partial | `type_aliases` | `name, line_number` | `none:not_persisted` | `tests/unit/parsers/test_typescriptjsx_parser.py::test_parse_tsx_imports_calls_variables_and_type_aliases` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_type_alias_nodes_not_created` | TSX files inherit TypeScript type-alias extraction, but those alias definitions are not yet persisted into graph nodes. |
| JSX component usage | `jsx-component-usage` | partial | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_typescriptjsx_parser.py::test_parse_tsx_components_and_interfaces` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_call_edges_created` | JSX tag usage is approximated through call-like capture paths, but there is no dedicated component-reference model or TSX-specific query surface. |

## Known Limitations
- JSX element tag names are not modeled as distinct component reference nodes
- Fragment shorthand (`<>...</>`) is not separately tracked
- TSX-specific type narrowing patterns (e.g., `as ComponentType`) are not captured
