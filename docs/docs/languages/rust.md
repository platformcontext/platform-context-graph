# Rust Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `rust`
- Family: `language`
- Parser: `DefaultEngine (rust)`
- Entrypoint: `go/internal/parser/rust_language.go`
- Fixture repo: `tests/fixtures/ecosystems/rust_comprehensive/`
- Unit test suite: `go/internal/parser/engine_systems_test.go`
- Integration validation: compose-backed fixture verification (see `../reference/local-testing.md`)

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathRust` | Compose-backed fixture verification | - |
| Structs | `structs` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathRust` | Compose-backed fixture verification | - |
| Enums | `enums` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathRust` | Compose-backed fixture verification | - |
| Traits | `traits` | supported | `traits` | `name, line_number` | `node:Trait` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathRust` | Compose-backed fixture verification | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathRust` | Compose-backed fixture verification | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathRust` | Compose-backed fixture verification | - |
| Method calls (field expressions) | `method-calls-field-expressions` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathRust` | Compose-backed fixture verification | - |
| Scoped calls (path::fn) | `scoped-calls-path-fn` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathRust` | Compose-backed fixture verification | - |
| Impl blocks | `impl-blocks` | partial | `impl_context` | `name, line_number` | `property:Function.context` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathRustImplOwnership` | Compose-backed fixture verification | Impl ownership is attached as function context, but impl blocks are not persisted as dedicated graph nodes or explicit implementation edges. |

## Known Limitations
- `impl Trait for Type` implementations are not tracked as distinct graph edges
- Lifetime annotations are not captured
- Macro-generated code is not traversed
