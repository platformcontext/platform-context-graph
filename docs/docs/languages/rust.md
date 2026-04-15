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
| Impl blocks | `impl-blocks` | partial | `impl_blocks` | `name, line_number, kind` | `content:ImplBlock entity + code/language-query + entity-context + code/relationships` | `go/internal/parser/engine_systems_test.go::TestDefaultEngineParsePathRustImplBlocks`, `go/internal/parser/engine_rust_lifetimes_test.go::TestDefaultEngineParsePathRustCapturesImplLifetimes`, `go/internal/query/language_queries_test.go::TestHandleLanguageQuery_ContentBackedEntityTypes`, `go/internal/query/entity_content_fallback_test.go::TestGetEntityContextFallsBackToContentRustImplBlockContext`, `go/internal/query/code_relationships_content_fallback_test.go::TestHandleRelationshipsFallsBackToContentRustImplBlockOwnership`, `go/internal/query/content_relationships_rust_test.go::TestBuildContentRelationshipSetRustImplBlockContainsMethods` | Compose-backed fixture verification | The Go parser now emits dedicated impl block records, preserves bounded lifetime metadata on impl signatures, the content layer persists them as `ImplBlock` entities, and the normal Go `code/language-query`, entity-context, and `code/relationships` surfaces can expose impl ownership through exact `impl_context` matching. The remaining gap is graph-first persistence of explicit implementation edges, not parser or normal query-path ownership. |

## Known Limitations
- `impl Trait for Type` implementations are emitted into `impl_blocks` and persisted as `ImplBlock` content entities, but the graph layer does not yet persist explicit implementation edges
- Bounded lifetime metadata is preserved on function and impl signatures, but
  lifetime-aware graph semantics are not yet first-class beyond parser/query
  metadata
- Macro-generated code is not traversed
