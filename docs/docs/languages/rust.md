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
| Impl blocks | `impl-blocks` | partial | `impl_blocks` | `name, line_number, kind` | `content:ImplBlock entity` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathRustImplBlocks` | Compose-backed fixture verification | The Go parser now emits dedicated impl block records, the content layer persists them as `ImplBlock` entities, and function `impl_context` remains available, but graph/story surfacing still does not expose explicit implementation edges end to end. |

## Known Limitations
- `impl Trait for Type` implementations are emitted into `impl_blocks` and persisted as `ImplBlock` content entities, but the graph layer does not yet persist explicit implementation edges
- Lifetime annotations are not captured
- Macro-generated code is not traversed
