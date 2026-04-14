# Elixir Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `elixir`
- Family: `language`
- Parser: `DefaultEngine (elixir)`
- Entrypoint: `go/internal/parser/elixir_dart_language.go`
- Fixture repo: `tests/fixtures/ecosystems/elixir_comprehensive/`
- Unit test suite: `go/internal/parser/engine_elixir_semantics_test.go`
- Integration validation: compose-backed fixture verification (see `../reference/local-testing.md`)

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions (`def`/`defp`) | `functions-def-defp` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirFunctionMetadata` | Compose-backed fixture verification | - |
| Macros (`defmacro`/`defmacrop`) | `macros-defmacro-defmacrop` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirFunctionMetadata` | Compose-backed fixture verification | - |
| Guards (`defguard`/`defguardp`) | `guards-defguard-defguardp` | partial | `functions` | `name, line_number` | `node:Function + semantic_summary` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirFunctionMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryElixirFunctionKinds` | Compose-backed fixture verification | The Go parser emits guard definitions into the normalized `functions` bucket with `semantic_kind=guard`, and normal Go query/context responses now synthesize semantic summaries from that metadata. The graph surface still does not persist them as first-class guard semantics end to end. |
| Delegated functions (`defdelegate`) | `delegated-functions-defdelegate` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirFunctionMetadata` | Compose-backed fixture verification | - |
| Modules (`defmodule`) | `modules-defmodule` | supported | `modules` | `name, line_number` | `node:Module` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirModuleKindsAndFunctionKinds` | Compose-backed fixture verification | - |
| Protocols (`defprotocol`) | `protocols-defprotocol` | partial | `modules` | `name, line_number` | `node:Module + semantic_summary` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirModuleKindsAndFunctionKinds` | Compose-backed fixture verification | Protocol declarations are extracted and now carry `module_kind=protocol`, while normal Go query/context responses can summarize that metadata. The persisted graph still does not retain a first-class protocol node. |
| Protocol implementations (`defimpl`) | `protocol-implementations-defimpl` | partial | `modules` | `name, line_number` | `node:Module + semantic_summary` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirModuleKindsAndFunctionKinds`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryElixirModule` | Compose-backed fixture verification | Protocol implementations are extracted and now carry `module_kind=protocol_implementation` plus `protocol`/`implemented_for`, and normal Go query/context responses can summarize that metadata. The graph still merges them into generic Module nodes. |
| Use/import/alias/require | `use-import-alias-require` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirImportAndCallMetadata` | Compose-backed fixture verification | - |
| Dot-notation calls | `dot-notation-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirImportAndCallMetadata` | Compose-backed fixture verification | - |
| Simple function calls | `simple-function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirImportAndCallMetadata` | Compose-backed fixture verification | - |
| Module attributes (`@attr`) | `module-attributes-attr` | partial | `variables` | `name, line_number` | `node:Variable + semantic_summary` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirEmitsModuleAttributes` | Compose-backed fixture verification | The Go parser emits module attributes into the normalized parser payload with `attribute_kind=module_attribute`, and normal Go query/context responses can summarize that metadata. The graph does not yet persist them as dedicated variable nodes end to end. |

## Known Limitations
- Multiple function clause heads for the same function are each captured as separate entries
- Pipe operator (`|>`) chains are not collapsed into a single call chain node
- GenServer callbacks are not distinguished from regular function definitions
