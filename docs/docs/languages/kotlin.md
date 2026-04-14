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
- Integration validation: compose-backed fixture verification (see `../reference/local-testing.md`)

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | Compose-backed fixture verification | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | Compose-backed fixture verification | - |
| Objects (`object`) | `objects-object` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | Compose-backed fixture verification | - |
| Companion objects | `companion-objects` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | Compose-backed fixture verification | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | Compose-backed fixture verification | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | Compose-backed fixture verification | - |
| Property declarations | `property-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | Compose-backed fixture verification | - |
| Class context on functions | `class-context-on-functions` | supported | `functions` | `name, line_number, class_context` | `property:Function.class_context` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathKotlinFixtures` | Compose-backed fixture verification | - |
| Secondary constructors | `secondary-constructors` | partial | `functions` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_managed_oo_test.go::TestDefaultEngineParsePathKotlinSecondaryConstructors` | Compose-backed fixture verification | Secondary constructor syntax is parsed as part of class structure, but constructor-specific graph nodes or relationships are not persisted yet. |

## Known Limitations
- Kotlin interfaces are not separately bucketed from classes
- Extension functions are captured as regular functions without extension receiver tracking
- Coroutine suspend functions do not carry a suspend flag in the output
