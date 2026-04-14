# PHP Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `php`
- Family: `language`
- Parser: `DefaultEngine (php)`
- Entrypoint: `go/internal/parser/php_language.go`
- Fixture repo: `tests/fixtures/ecosystems/php_comprehensive/`
- Unit test suite: `go/internal/parser/php_language_test.go`
- Integration validation: compose-backed fixture verification (see `../reference/local-testing.md`)

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsFunctionParametersSourceAndContext` | Compose-backed fixture verification | - |
| Methods | `methods` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsFunctionParametersSourceAndContext` | Compose-backed fixture verification | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsInheritanceAndImportMetadata` | Compose-backed fixture verification | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsInheritanceAndImportMetadata` | Compose-backed fixture verification | - |
| Traits | `traits` | supported | `traits` | `name, line_number` | `node:Trait` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathPHPFixtures` | Compose-backed fixture verification | - |
| Use declarations | `use-declarations` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsInheritanceAndImportMetadata` | Compose-backed fixture verification | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsVariableAndCallMetadata` | Compose-backed fixture verification | - |
| Member method calls | `member-method-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsVariableAndCallMetadata` | Compose-backed fixture verification | - |
| Static method calls | `static-method-calls` | partial | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsVariableAndCallMetadata` | Compose-backed fixture verification | Static call syntax is covered in focused parser tests, but the comprehensive fixture repo currently proves only member-call and constructor-call graph edges end to end. |
| Object creation (`new`) | `object-creation-new` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsVariableAndCallMetadata` | Compose-backed fixture verification | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/php_language_test.go::TestDefaultEngineParsePathPHPEmitsVariableAndCallMetadata` | Compose-backed fixture verification | - |

## Known Limitations
- Trait `use` inside class bodies is not linked as an INHERITS relationship
- Anonymous classes are not modeled as distinct nodes
- Magic methods (`__get`, `__call`) are captured as regular methods without special classification
