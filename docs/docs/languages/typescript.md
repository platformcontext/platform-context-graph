# TypeScript Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/typescript.yaml`

## Parser Contract
- Language: `typescript`
- Family: `language`
- Parser: `DefaultEngine (typescript)`
- Entrypoint: `go/internal/parser/javascript_language.go`
- Fixture repo: `tests/fixtures/ecosystems/typescript_comprehensive/`
- Unit test suite: `go/internal/parser/engine_javascript_semantics_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestTypeScriptGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `enums` | `name, line_number` | `node:Enum` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTypeScriptSemanticsAndTypes` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_runtime_surface` | - |
| Type aliases | `type-aliases` | partial | `type_aliases` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTypeScriptDecoratorAndGenericParity` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_function_nodes_created` | Type aliases are extracted into a dedicated parse bucket, but the persistence layer does not currently materialize TypeAlias graph nodes. |
| Decorators | `decorators` | unsupported | `classes` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTypeScriptDecoratorAndGenericParity` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_decorator_metadata_not_persisted` | The Go parser now emits decorator metadata, but the graph surface still does not persist decorators as first-class queryable properties. |
| Generics | `generics` | partial | `type_parameters` | `name, line_number, type_parameters` | `none:not_persisted` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTypeScriptDecoratorAndGenericParity` | `tests/integration/test_language_graph.py::TestTypeScriptGraph::test_function_nodes_created` | The Go parser emits type parameter metadata, but the graph surface does not yet promote generic information into a dedicated query model. |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `supported`
- Framework packs: `react-base`, `nextjs-app-router-base`, `express-base`, `hapi-base`, `aws-sdk-base`, `gcp-sdk-base`
- Query surfacing: `supported`
- Real-repo validation: `supported`
- End-to-end indexing: `supported`
- Local repo validation evidence:
  - `api-node-platform (109 indexed TS files, clean end-to-end validation on a zero-TSX repo)`
- Notes:
  - api-node-platform completed a clean local end-to-end indexing run (run ef02081cb9874275)
  - repo context, repo summary, and repo story all returned successfully on a pure TypeScript repo without requiring framework evidence
  - TypeScript now participates in the same declarative Node HTTP and provider-pack program as JavaScript
  - generic type aliases and decorators remain partial or unsupported as documented below


## Known Limitations
- Type aliases are parsed (`type_aliases` key) but not persisted to the graph — no persistence mapping exists
- Mapped types and conditional types not fully captured
- Namespace declarations may be incomplete
- Declaration merging not tracked
