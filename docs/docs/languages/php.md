# PHP Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/php.yaml`

## Parser Contract
- Language: `php`
- Family: `language`
- Parser: `DefaultEngine (php)`
- Entrypoint: `go/internal/parser/php_language.go`
- Fixture repo: `tests/fixtures/ecosystems/php_comprehensive/`
- Unit test suite: `go/internal/parser/php_language_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestPhpGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsFunctionParametersSourceAndContext` | `tests/integration/test_language_graph.py::TestPhpGraph::test_runtime_surface` | - |
| Methods | `methods` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsFunctionParametersSourceAndContext` | `tests/integration/test_language_graph.py::TestPhpGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsInheritanceAndImportMetadata` | `tests/integration/test_language_graph.py::TestPhpGraph::test_runtime_surface` | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsInheritanceAndImportMetadata` | `tests/integration/test_language_graph.py::TestPhpGraph::test_runtime_surface` | - |
| Traits | `traits` | supported | `traits` | `name, line_number` | `node:Trait` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathPHPFixtures` | `tests/integration/test_language_graph.py::TestPhpGraph::test_runtime_surface` | - |
| Use declarations | `use-declarations` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsInheritanceAndImportMetadata` | `tests/integration/test_language_graph.py::TestPhpGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsVariableAndCallMetadata` | `tests/integration/test_language_graph.py::TestPhpGraph::test_runtime_surface` | - |
| Member method calls | `member-method-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsVariableAndCallMetadata` | `tests/integration/test_language_graph.py::TestPhpGraph::test_runtime_surface` | - |
| Static method calls | `static-method-calls` | partial | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsVariableAndCallMetadata` | `tests/integration/test_language_graph.py::TestPhpGraph::test_runtime_surface` | Static call syntax is covered in focused parser tests, but the comprehensive fixture repo currently proves only member-call and constructor-call graph edges end to end. |
| Object creation (`new`) | `object-creation-new` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsVariableAndCallMetadata` | `tests/integration/test_language_graph.py::TestPhpGraph::test_runtime_surface` | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsVariableAndCallMetadata` | `tests/integration/test_language_graph.py::TestPhpGraph::test_runtime_surface` | - |

## Known Limitations
- Trait `use` inside class bodies is not linked as an INHERITS relationship
- Anonymous classes are not modeled as distinct nodes
- Magic methods (`__get`, `__call`) are captured as regular methods without special classification
