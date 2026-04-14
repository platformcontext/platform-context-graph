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
| JSDoc comments | `jsdoc-comments` | partial | `functions` | `name, line_number, docstring` | `content:Entity.metadata.docstring` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathJavaScriptDocstringsAndMethodKinds`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata` | Compose-backed fixture verification | The Go parser emits docstring metadata, the content pipeline preserves it, and graph-backed `language-query`, `code/search`, `entities/resolve`, and entity-context responses now enrich matching rows with that metadata. What remains partial is first-class graph/story/context surfacing beyond those API responses. |
| Method kind (get/set/async) | `method-kind-get-set-async` | partial | `functions` | `name, line_number, type` | `content:Entity.metadata.type` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathJavaScriptDocstringsAndMethodKinds`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata` | Compose-backed fixture verification | Getter, setter, and async method kinds are captured and preserved in entity metadata, and graph-backed `language-query`, `code/search`, `entities/resolve`, and entity-context responses now enrich matching rows with that metadata. What remains partial is broader graph/story/context promotion. |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `supported`
- Framework packs: `react-base`, `nextjs-app-router-base`, `express-base`, `hapi-base`, `aws-sdk-base`, `gcp-sdk-base`
- Query surfacing: `partial`
- Real-repo validation: `supported`
- End-to-end indexing: `supported`
- Notes:
  - Real-repo validation covers React, Next.js, Express, Hapi, and bounded AWS
    and GCP SDK evidence through the Go-owned parser and indexing path.
  - JSDoc and method-kind semantics already survive parse and content
    materialization, and graph-backed `language-query`, `code/search`,
    `entities/resolve`, and entity-context results now surface the matching
    metadata. Broader graph/story/context surfacing is still partial.


## Known Limitations
- Computed property names in classes are not resolved to static names
- Dynamic `require()` calls with non-literal paths are not tracked
- Generator functions are captured as regular functions without generator flag
