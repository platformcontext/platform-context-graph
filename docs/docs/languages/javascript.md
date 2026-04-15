# JavaScript Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `javascript`
- Family: `language`
- Parser: `DefaultEngine (javascript)`
- Entrypoint: `go/internal/parser/javascript_language.go`
- Fixture repo: `tests/fixtures/ecosystems/javascript_comprehensive/`
- Unit test suite: `go/internal/parser/engine_javascript_semantics_test.go`
- Integration validation: compose-backed fixture verification (see `../reference/local-testing.md`)

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Function declarations | `function-declarations` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathJavaScript` | Compose-backed fixture verification | - |
| Function expressions | `function-expressions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathJavaScript` | Compose-backed fixture verification | - |
| Arrow functions (named) | `arrow-functions-named` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathJavaScript` | Compose-backed fixture verification | - |
| Method definitions | `method-definitions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathJavaScript` | Compose-backed fixture verification | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathJavaScript` | Compose-backed fixture verification | - |
| Imports (`import`/`require`) | `imports-import-require` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathJavaScript` | Compose-backed fixture verification | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathJavaScript` | Compose-backed fixture verification | - |
| Member call expressions | `member-call-expressions` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathJavaScript` | Compose-backed fixture verification | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathJavaScript` | Compose-backed fixture verification | - |
| JSDoc comments | `jsdoc-comments` | partial | `functions` | `name, line_number, docstring` | `content:Entity.metadata.docstring + code/language/entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathJavaScriptDocstringsAndMethodKinds`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadataJavaScriptMethod`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryJavaScriptFunction`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsJavaScriptMethodSignals` | Compose-backed fixture verification | The Go parser emits docstring metadata, the content pipeline preserves it, graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context responses enrich matching rows with that metadata, `language-query`, `code/search`, plus entity-context emit both a first-class semantic summary and a structured `semantic_profile`, entity-context now also emits a first-class `story`, and repository stories now carry a semantic overview derived from those same entities. JavaScript method-kind rows now also get a dedicated `javascript_method` surface kind in the shared semantic profile. What remains partial is dedicated graph-first promotion beyond the shared query/story surfaces. |
| Method kind (get/set/async) | `method-kind-get-set-async` | partial | `functions` | `name, line_number, type` | `content:Entity.metadata.type + code/language/entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathJavaScriptDocstringsAndMethodKinds`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadataJavaScriptMethod`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryJavaScriptFunction`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsJavaScriptMethodSignals` | Compose-backed fixture verification | Getter, setter, and async method kinds are captured and preserved in entity metadata, graph-backed query surfaces enrich matching rows with that metadata, `language-query`, `code/search`, plus entity-context emit both a first-class semantic summary and a structured `semantic_profile`, entity-context now also emits a first-class `story`, and repository stories now carry a semantic overview derived from those same entities. JavaScript method-kind rows now also get a dedicated `javascript_method` surface kind in the shared semantic profile. What remains partial is dedicated graph-first promotion beyond the shared query/story surfaces. |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `supported`
- Framework packs: `react-base`, `nextjs-app-router-base`, `express-base`, `hapi-base`, `aws-sdk-base`, `gcp-sdk-base`
- Query surfacing: `supported`
- Real-repo validation: `supported`
- End-to-end indexing: `supported`
- Notes:
  - Real-repo validation covers React, Next.js, Express, Hapi, and bounded AWS
    and GCP SDK evidence through the Go-owned parser and indexing path.
  - JSDoc and method-kind semantics already survive parse and content
    materialization, and graph-backed `language-query`, `code/search`,
    `dead-code`, `code/relationships`, `code/complexity`,
    `entities/resolve`, and entity-context results now surface the matching
    metadata. `language-query`, `code/search`, and entity-context also emit
    both semantic summaries and a structured `semantic_profile` for
    JavaScript functions when docstring or method-kind metadata is present,
    JavaScript method-kind rows now get a dedicated `javascript_method`
    surface kind, entity-context now emits a first-class `story`, and
    repository stories now expose a semantic overview derived from those
    entities. Dedicated graph-first promotion is still partial.


## Known Limitations
- Computed property names in classes are not resolved to static names
- Dynamic `require()` calls with non-literal paths are not tracked
- Generator functions are captured as regular functions without generator flag
