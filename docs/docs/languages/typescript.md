# TypeScript Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/typescript.yaml`

## Parser Contract
- Language: `typescript`
- Family: `language`
- Parser: `TypescriptTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/typescript.py`
- Fixture repo: `tests/fixtures/ecosystems/typescript_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_typescript_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestTypeScriptGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_typescript_parser.py::test_parse_functions` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_typescript_parser.py::test_parse_classes` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `tests/unit/parsers/test_typescript_parser.py::test_parse_interfaces` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_typescript_parser.py::test_parse_imports` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_typescript_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_typescript_parser.py::test_parse_variables` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `enums` | `name, line_number` | `node:Enum` | `tests/unit/parsers/test_typescript_parser.py::test_parse_enums` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Type aliases | `type-aliases` | partial | `type_aliases` | `name, line_number` | `none:not_persisted` | `tests/unit/parsers/test_typescript_parser.py::test_parse_type_aliases` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_function_nodes_created` | Type aliases are extracted into a dedicated parse bucket, but the persistence layer does not currently materialize TypeAlias graph nodes. |
| Decorators | `decorators` | unsupported | `classes` | `name, line_number` | `none:not_persisted` | `tests/unit/parsers/test_typescript_parser.py::test_parse_decorators_do_not_emit_metadata` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_decorator_metadata_not_persisted` | Decorator syntax is accepted by the parser, but decorator metadata is not emitted into the normalized parse result or persisted to graph properties. |
| Generics | `generics` | partial | `type_parameters` | `name, line_number, type_parameters` | `none:not_persisted` | `tests/unit/parsers/test_typescript_parser.py::test_parse_generics` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_function_nodes_created` | Generic syntax is tolerated in parsed declarations, but type parameter metadata is not promoted into the normalized graph model. |

## Known Limitations
- Type aliases are parsed (`type_aliases` key) but not persisted to the graph — no persistence mapping exists
- Mapped types and conditional types not fully captured
- Namespace declarations may be incomplete
- Declaration merging not tracked
