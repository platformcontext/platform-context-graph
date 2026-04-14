# Dart Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/dart.yaml`

## Parser Contract
- Language: `dart`
- Family: `language`
- Parser: `DefaultEngine (dart)`
- Entrypoint: `go/internal/parser/elixir_dart_language.go`
- Fixture repo: `tests/fixtures/ecosystems/dart_comprehensive/`
- Unit test suite: `go/internal/parser/engine_long_tail_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestDartGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathDartFixtures` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Constructors | `constructors` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathDartFixtures` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathDartFixtures` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Mixins | `mixins` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathDartFixtures` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Extensions | `extensions` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathDartFixtures` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathDartFixtures` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Library imports | `library-imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathDartFixtures` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Library exports | `library-exports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathDartFixtures` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathDartFixtures` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Local variable declarations | `local-variable-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathDartFixtures` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Top-level variable declarations | `top-level-variable-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathDartFixtures` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |

## Known Limitations
- Named constructors (`ClassName.named(...)`) are captured under the constructor name only
- Cascade notation (`..method()`) is not tracked as a distinct call chain
- `part`/`part of` directives are not modeled as import relationships
