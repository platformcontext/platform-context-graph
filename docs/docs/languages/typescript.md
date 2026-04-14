# TypeScript Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `typescript`
- Family: `language`
- Parser: `DefaultEngine (typescript)`
- Entrypoint: `go/internal/parser/javascript_language.go`
- Fixture repo: `tests/fixtures/ecosystems/typescript_comprehensive/`
- Unit test suite: `go/internal/parser/engine_javascript_semantics_test.go`
- Integration validation: compose-backed fixture verification (see `../reference/local-testing.md`)

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | Compose-backed fixture verification | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | Compose-backed fixture verification | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | Compose-backed fixture verification | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | Compose-backed fixture verification | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | Compose-backed fixture verification | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathTypeScript` | Compose-backed fixture verification | - |
| Enums | `enums` | supported | `enums` | `name, line_number` | `node:Enum` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTypeScriptSemanticsAndTypes` | Compose-backed fixture verification | - |
| Type aliases | `type-aliases` | partial | `type_aliases` | `name, line_number` | `content:TypeAlias entity` | `go/internal/query/language_queries_test.go::TestHandleLanguageQuery_ContentBackedEntityTypes`, `go/internal/query/entity_content_fallback_test.go::TestResolveEntityFallsBackToContentEntities`, `go/internal/query/content_reader_test.go::TestCodeHandlerSearchEntityContentIncludesEntityNameMatches` | Compose-backed fixture verification | Type aliases are queryable through the Go content-backed language-query and content APIs, the normal entity resolve/context surfaces now fall back to content-backed entities, and the normal `code/search` fallback now searches content-backed entity names as well as source text. What remains partial is dedicated graph/story surfacing and first-class graph modeling. |
| Decorators | `decorators` | partial | `classes` | `name, line_number` | `content:Entity.metadata.decorators` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTypeScriptDecoratorAndGenericParity`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata` | Compose-backed fixture verification | Decorator metadata is emitted and preserved in content entities, and graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context responses now enrich matching rows with that metadata. What remains partial is dedicated graph/story/context surfacing. |
| Generics | `generics` | partial | `type_parameters` | `name, line_number, type_parameters` | `content:Entity.metadata.type_parameters` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTypeScriptDecoratorAndGenericParity`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata` | Compose-backed fixture verification | Type parameter metadata is preserved in content entities and can now flow into graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context responses for matching entities. What remains partial is first-class graph/story/context modeling beyond those API responses. |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `supported`
- Framework packs: `react-base`, `nextjs-app-router-base`, `express-base`, `hapi-base`, `aws-sdk-base`, `gcp-sdk-base`
- Query surfacing: `partial`
- Real-repo validation: `supported`
- End-to-end indexing: `supported`
- Notes:
  - Real-repo validation covers pure TypeScript repositories without requiring
    TSX-specific framework evidence.
  - TypeScript participates in the same declarative Node HTTP and provider-pack
    program as JavaScript.
  - Type aliases are queryable through the Go content-backed APIs, the normal
    entity resolve/context surfaces now fall back to content-backed entities,
    and the normal `code/search` fallback now searches content-backed entity
    names as well as source text. Graph-backed `language-query`, `code/search`, `dead-code`,
    `code/relationships`, `code/complexity`, `entities/resolve`, and
    entity-context results also enrich matching class/function rows with
    decorator and generic metadata. Dedicated graph/story/context surfacing
    remains partial.


## Known Limitations
- Type aliases are queryable through the Go content-backed APIs and discoverable through the normal `code/search` fallback, but graph/story/context surfacing remains partial
- Mapped types and conditional types not fully captured
- Namespace declarations may be incomplete
- Declaration merging not tracked
