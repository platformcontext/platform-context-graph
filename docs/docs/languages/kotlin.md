# Kotlin Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `kotlin`
- Family: `language`
- Parser: `DefaultEngine (kotlin)`
- Entrypoint: `go/internal/parser/kotlin_language.go`
- Fixture repo: `tests/fixtures/ecosystems/kotlin_comprehensive/`
- Unit test suite: `go/internal/parser/engine_managed_oo_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestKotlinGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Objects (`object`) | `objects-object` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Companion objects | `companion-objects` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Property declarations | `property-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Class context on functions | `class-context-on-functions` | supported | `functions` | `name, line_number, class_context` | `property:Function.class_context` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Secondary constructors | `secondary-constructors` | partial | `functions` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathKotlinSecondaryConstructors` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_class_nodes` | Secondary constructor syntax is parsed as part of class structure, but constructor-specific graph nodes or relationships are not persisted yet. |

## Known Limitations
- Kotlin interfaces are not separately bucketed from classes
- Extension functions are captured as regular functions without extension receiver tracking
- Coroutine suspend functions do not carry a suspend flag in the output
