# C Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `c`
- Family: `language`
- Parser: `DefaultEngine (c)`
- Entrypoint: `go/internal/parser/c_language.go`
- Fixture repo: `tests/fixtures/ecosystems/c_comprehensive/`
- Unit test suite: `go/internal/parser/engine_systems_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestCGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathC` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Pointer-returning functions | `pointer-returning-functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathC` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Structs | `structs` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathC` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Unions | `unions` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathCTypedefAliases` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathC` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Typedefs | `typedefs` | partial | `typedefs` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathCTypedefAliasEmitsDedicatedEntities` | `tests/integration/test_language_graph.py::TestCGraph::test_typedef_nodes_not_created` | The Go parser emits dedicated typedef entities, but the graph layer does not yet materialize Typedef nodes end to end. |
| Includes | `includes` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathC` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathC` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Variables (initialized declarations) | `variables-initialized-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathC` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |
| Macros (`#define`) | `macros-define` | supported | `macros` | `name, line_number` | `node:Macro` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathC` | `tests/integration/test_language_graph.py::TestCGraph::test_runtime_surface` | - |

## Known Limitations
- Function pointer declarations are not modeled as callable entities
- Preprocessor macros with complex expansions are captured by name only
- Variadic functions do not expose their variadic argument types
