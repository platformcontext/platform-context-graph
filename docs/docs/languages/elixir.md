# Elixir Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/elixir.yaml`

## Parser Contract
- Language: `elixir`
- Family: `language`
- Parser: `DefaultEngine (elixir)`
- Entrypoint: `go/internal/parser/elixir_dart_language.go`
- Fixture repo: `tests/fixtures/ecosystems/elixir_comprehensive/`
- Unit test suite: `go/internal/parser/engine_elixir_semantics_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestElixirGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions (`def`/`defp`) | `functions-def-defp` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirFunctionMetadata` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Macros (`defmacro`/`defmacrop`) | `macros-defmacro-defmacrop` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirFunctionMetadata` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Guards (`defguard`/`defguardp`) | `guards-defguard-defguardp` | partial | `functions` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirFunctionMetadata` | `tests/integration/test_language_graph.py::TestElixirGraph::test_guard_definitions_not_persisted_as_functions` | The Go parser emits guard definitions into the normalized `functions` bucket, but the graph surface does not yet persist them as Function nodes end to end. |
| Delegated functions (`defdelegate`) | `delegated-functions-defdelegate` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirFunctionMetadata` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Modules (`defmodule`) | `modules-defmodule` | supported | `modules` | `name, line_number` | `node:Module` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirModuleKindsAndFunctionKinds` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Protocols (`defprotocol`) | `protocols-defprotocol` | partial | `modules` | `name, line_number` | `node:Module` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirModuleKindsAndFunctionKinds` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | Protocol declarations are extracted and merged into generic Module nodes, but the persisted graph does not retain the `defprotocol` kind needed for end-to-end protocol-specific queries. |
| Protocol implementations (`defimpl`) | `protocol-implementations-defimpl` | partial | `modules` | `name, line_number` | `node:Module` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirModuleKindsAndFunctionKinds` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | Protocol implementations are extracted, but the graph merges them into undifferentiated Module nodes and drops the `defimpl` type marker. |
| Use/import/alias/require | `use-import-alias-require` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirImportAndCallMetadata` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Dot-notation calls | `dot-notation-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirImportAndCallMetadata` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Simple function calls | `simple-function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirImportAndCallMetadata` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Module attributes (`@attr`) | `module-attributes-attr` | partial | `variables` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_elixir_semantics_test.go::TestDefaultEngineParsePathElixirEmitsModuleAttributes` | `tests/integration/test_language_graph.py::TestElixirGraph::test_module_attributes_not_persisted` | The Go parser emits module attributes into the normalized parser payload, but the graph does not yet persist them as dedicated variable nodes end to end. |

## Known Limitations
- Multiple function clause heads for the same function are each captured as separate entries
- Pipe operator (`|>`) chains are not collapsed into a single call chain node
- GenServer callbacks are not distinguished from regular function definitions
