# Java Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `java`
- Family: `language`
- Parser: `DefaultEngine (java)`
- Entrypoint: `go/internal/parser/java_language.go`
- Fixture repo: `tests/fixtures/ecosystems/java_comprehensive/`
- Unit test suite: `go/internal/parser/engine_managed_oo_test.go`
- Integration validation: compose-backed fixture verification (see `../reference/local-testing.md`)

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Methods | `methods` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJava` | Compose-backed fixture verification | - |
| Constructors | `constructors` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJava` | Compose-backed fixture verification | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJava` | Compose-backed fixture verification | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJava` | Compose-backed fixture verification | - |
| Enums | `enums` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJava` | Compose-backed fixture verification | - |
| Annotation types | `annotation-types` | supported | `annotations` | `name, line_number` | `node:Annotation` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJavaAnnotationMetadata` | Compose-backed fixture verification | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJava` | Compose-backed fixture verification | - |
| Method invocations | `method-invocations` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJava` | Compose-backed fixture verification | - |
| Object creation | `object-creation` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJava` | Compose-backed fixture verification | - |
| Local variables | `local-variables` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJava` | Compose-backed fixture verification | - |
| Field declarations | `field-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJava` | Compose-backed fixture verification | - |
| Annotations (applied) | `annotations-applied` | partial | `annotations` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathJavaAnnotationMetadata` | Compose-backed fixture verification | Annotation declarations are indexed, but annotation usage on classes, methods, and fields is not persisted as a first-class graph surface. |

## Known Limitations
- Generic type bounds and wildcards not captured as structured data
- Anonymous inner classes not separately tracked
- Lambda expressions not individually modeled as functions
