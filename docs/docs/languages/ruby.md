# Ruby Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `ruby`
- Family: `language`
- Parser: `DefaultEngine (ruby)`
- Entrypoint: `go/internal/parser/ruby_language.go`
- Fixture repo: `tests/fixtures/ecosystems/ruby_comprehensive/`
- Unit test suite: `go/internal/parser/engine_ruby_semantics_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestRubyGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Methods (`def`) | `methods-def` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathRubyFixtures` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathRubyFixtures` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Modules | `modules` | supported | `modules` | `name, line_number` | `node:Module` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathRubyFixtures` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Require/load imports | `require-load-imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_ruby_semantics_test.go::TestDefaultEngineParsePathRubyEmitsRequireAndLoadImports` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Method calls | `method-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_ruby_semantics_test.go::TestDefaultEngineParsePathRubyCapturesGenericDslAndMethodCalls` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Instance variable assignments | `instance-variable-assignments` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_ruby_semantics_test.go::TestDefaultEngineParsePathRubyCapturesLocalAndInstanceAssignments` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Local variable assignments | `local-variable-assignments` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_ruby_semantics_test.go::TestDefaultEngineParsePathRubyCapturesLocalAndInstanceAssignments` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Module inclusions (`include`/`extend`) | `module-inclusions-include-extend` | supported | `module_inclusions` | `class, module, line_number` | `relationship:INCLUDES` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathRubyFixtures` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Parent context (class/module) | `parent-context-class-module` | supported | `functions` | `name, line_number, class_context` | `property:Function.class_context` | `go/internal/parser/engine_ruby_semantics_test.go::TestDefaultEngineParsePathRubyEmitsFunctionArgsAndContext` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |

## Known Limitations
- Singleton methods (defined on specific objects) are not separated from instance methods
- `method_missing` based dynamic dispatch is not tracked
- DSL-style method definitions (e.g., ActiveRecord scopes) are captured as regular calls only
