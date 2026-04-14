# Swift Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `swift`
- Family: `language`
- Parser: `DefaultEngine (swift)`
- Entrypoint: `go/internal/parser/swift_language.go`
- Fixture repo: `tests/fixtures/ecosystems/swift_comprehensive/`
- Unit test suite: `go/internal/parser/engine_swift_semantics_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestSwiftGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_swift_semantics_test.go::TestDefaultEngineParsePathSwiftEmitsBasesAndFunctionArgs` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Initializers (`init`) | `initializers-init` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_swift_semantics_test.go::TestDefaultEngineParsePathSwiftEmitsImportAndCallMetadata` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathSwiftFixtures` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Structs | `structs` | supported | `structs` | `name, line_number` | `node:Struct` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathSwiftFixtures` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `enums` | `name, line_number` | `node:Enum` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathSwiftFixtures` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Protocols | `protocols` | supported | `protocols` | `name, line_number` | `node:Protocol` | `go/internal/parser/engine_swift_semantics_test.go::TestDefaultEngineParsePathSwiftInfersReceiverCallTypesAndEmitsProtocols` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Actors | `actors` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathSwiftFixtures` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_swift_semantics_test.go::TestDefaultEngineParsePathSwiftEmitsImportAndCallMetadata` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_swift_semantics_test.go::TestDefaultEngineParsePathSwiftEmitsImportAndCallMetadata` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Property declarations | `property-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_swift_semantics_test.go::TestDefaultEngineParsePathSwiftEmitsVariableContextAndTypeMetadata` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |

## Known Limitations
- Property wrappers are not tracked as distinct decorators
- `@objc` and dynamic dispatch attributes are not modeled in the graph
- Computed property bodies are not traversed for embedded function calls
