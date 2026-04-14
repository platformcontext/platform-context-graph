# TypeScript JSX Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/typescriptjsx.yaml`

## Parser Contract
- Language: `typescriptjsx`
- Family: `language`
- Parser: `DefaultEngine (tsx)`
- Entrypoint: `go/internal/parser/javascript_language.go`
- Fixture repo: `tests/fixtures/ecosystems/tsx_comprehensive/`
- Unit test suite: `go/internal/parser/engine_javascript_semantics_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXClassComponentParity` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_function_entities_created` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXSemanticsAndComponents` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_class_entities_created` | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXSemanticsAndComponents` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_interface_entities_created` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXSemanticsAndComponents` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_import_edges_created` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXJSXComponentUsageParity` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_call_edges_created` | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXSemanticsAndComponents` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_variable_nodes_created` | - |
| Type aliases | `type-aliases` | partial | `type_aliases` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXSemanticsAndComponents` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_type_alias_nodes_not_created` | TSX files inherit TypeScript type-alias extraction, but those alias definitions are not yet persisted into graph nodes. |
| JSX component usage | `jsx-component-usage` | partial | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXJSXComponentUsageParity` | `tests/integration/test_language_graph.py::TestTypeScriptJSXGraph::test_call_edges_created` | JSX tag usage is approximated through call-like capture paths, but there is no dedicated component-reference model or TSX-specific query surface. |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `supported`
- Framework packs: `react-base`, `nextjs-app-router-base`
- Query surfacing: `supported`
- Real-repo validation: `supported`
- End-to-end indexing: `supported`
- Local repo validation evidence:
  - `portal-nextjs-platform (612 indexed TSX files, 0 parser issues)`
  - `portal-java-ycm (358 indexed TSX files, 0 parser issues)`
  - `webapp-node-fsbo (177 indexed TSX files, 0 parser issues)`
  - `boats-chatgpt-app (local regression fixture plus clean TSX smoke check)`
- Notes:
  - portal-nextjs-platform completed a clean local end-to-end indexing run (run 01e7ca696a30df95)
  - repo context, repo summary, and repo story surfaced React/Next.js framework evidence through the default FalkorDB backend
  - the validation fixed two backend-compatibility gaps in repository graph counts and indexed file discovery


## Known Limitations
- JSX element tag names are not modeled as distinct component reference nodes
- Fragment shorthand (`<>...</>`) is not separately tracked
- TSX-specific type narrowing patterns (e.g., `as ComponentType`) are not captured
