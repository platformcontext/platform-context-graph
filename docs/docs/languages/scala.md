# Scala Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `scala`
- Family: `language`
- Parser: `DefaultEngine (scala)`
- Entrypoint: `go/internal/parser/scala_language.go`
- Fixture repo: `tests/fixtures/ecosystems/scala_comprehensive/`
- Unit test suite: `go/internal/parser/engine_managed_oo_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestScalaGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions (`def`) | `functions-def` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathScala` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathScala` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Objects (`object`) | `objects-object` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathScala` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Traits | `traits` | supported | `traits` | `name, line_number` | `node:Trait` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathScala` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathScala` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathScala` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Generic function calls | `generic-function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathScala` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Val definitions | `val-definitions` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathScala` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Var definitions | `var-definitions` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathScala` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |
| Parent context (class_context) | `parent-context-class-context` | supported | `functions` | `name, line_number, class_context` | `property:Function.class_context` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathScala` | `tests/integration/test_language_graph.py::TestScalaGraph::test_runtime_surface` | - |

## Known Limitations
- Implicit conversions and given/using clauses (Scala 3) are not separately tracked
- Pattern matching extractors are not modeled as function calls
- For-comprehension generators are not surfaced as variable bindings
