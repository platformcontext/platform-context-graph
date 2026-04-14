# C# Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `csharp`
- Family: `language`
- Parser: `DefaultEngine (c_sharp)`
- Entrypoint: `go/internal/parser/csharp_language.go`
- Fixture repo: `tests/fixtures/ecosystems/csharp_comprehensive/`
- Unit test suite: `go/internal/parser/engine_managed_oo_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestCSharpGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Methods | `methods` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharp` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Constructors | `constructors` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharp` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Local functions | `local-functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharpLocalTypes` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharp` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharp` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Structs | `structs` | supported | `structs` | `name, line_number` | `node:Struct` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharpLocalTypes` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Records | `records` | supported | `records` | `name, line_number` | `node:Record` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharp` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `enums` | `name, line_number` | `node:Enum` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharpLocalTypes` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Properties | `properties` | supported | `properties` | `name, line_number` | `node:Property` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharp` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_property_nodes` | - |
| Using directives | `using-directives` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharp` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Method invocations | `method-invocations` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharp` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Object creation | `object-creation` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharp` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_object_creation_calls` | - |
| Inheritance (`base_list`) | `inheritance-base-list` | supported | `classes` | `name, line_number, bases` | `relationship:INHERITS` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathCSharp` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_inheritance_edges` | - |

## Known Limitations
- Extension methods are not tagged as extensions in the graph
- Partial class merging across files is not performed
- Nullable reference types (`T?`) not surfaced as distinct type metadata
