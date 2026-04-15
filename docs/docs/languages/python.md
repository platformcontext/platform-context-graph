# Python Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `python`
- Family: `language`
- Parser: `DefaultEngine (python)`
- Entrypoint: `go/internal/parser/python_language.go`
- Fixture repo: `tests/fixtures/ecosystems/python_comprehensive/`
- Unit test suites: `go/internal/parser/engine_python_semantics_test.go`, `go/internal/parser/engine_python_metaclass_test.go`
- Integration validation: compose-backed fixture verification (see `../reference/local-testing.md`)

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Decorators | `decorators` | partial | `functions` | `name, line_number, decorators` | `graph:code/language-query metadata + content-backed code/search/entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonDecoratedFunctionsEmitDecoratorMetadata`, `go/internal/query/language_query_result_test.go::TestBuildLanguageResult_AttachesPythonGraphMetadataAndSemanticSummary`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadataPreservesPythonGraphMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonFunction`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | Decorator metadata is emitted on the Go parser path, `code/language-query` now projects it directly from graph rows, and the shared semantic summary/profile/story surfaces stay aligned when content fallback adds missing fields. `code/search`, entity-context, and repository stories still rely on the shared enrichment path rather than dedicated persisted decorator graph modeling. |
| Async functions | `async-functions` | partial | `functions` | `name, line_number, async` | `graph:code/language-query metadata + content-backed code/search/entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonAsyncFunctionsEmitAsyncFlag`, `go/internal/query/language_query_result_test.go::TestBuildLanguageResult_AttachesPythonGraphMetadataAndSemanticSummary`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonFunction`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | The async flag is emitted on the Go parser path, `code/language-query` now projects it directly from graph rows, and the shared semantic summary/profile/story surfaces keep that graph-owned value authoritative when content fallback also exists. Broader graph-first modeling beyond the current query/stories layer remains partial. |
| Lambda assignments | `lambda-assignments` | partial | `functions` | `name, line_number, semantic_kind=lambda` | `graph:code/language-query metadata + content-backed entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_python_metaclass_test.go::TestDefaultEngineParsePathPythonLambdaAssignmentEmitsNamedFunction`, `go/internal/query/python_semantics_promotion_test.go::TestPythonSemanticProfileFromMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonLambdaFunction`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | Identifier-assigned lambdas materialize as function entities with `semantic_kind=lambda`, and the normal semantic/profile/story surfaces now promote that consistently without any Python fallback. Inline lambdas that are not bound to a stable identifier remain ordinary expressions rather than first-class entities. |
| Metaclass relationships | `metaclass-relationships` | partial | `classes` | `name, line_number, metaclass` | `graph:code/language-query metadata + content:Entity.metadata.metaclass + code/relationships + entity_context.relationships` | `go/internal/parser/engine_python_metaclass_test.go::TestDefaultEngineParsePathPythonEmitsMetaclassMetadata`, `go/internal/query/language_query_result_test.go::TestBuildLanguageResult_AttachesPythonGraphMetadataAndSemanticSummary`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadataPreservesPythonGraphMetadata`, `go/internal/query/content_relationships_python_test.go::TestBuildContentRelationshipSetPythonClassUsesMetaclass`, `go/internal/query/content_relationships_python_test.go::TestBuildContentRelationshipSetPythonMetaclassHasIncomingUsage`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonMetaclassClass`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | Class entities now preserve `metaclass` metadata on the Go parser path, `code/language-query` projects that metadata directly from graph rows, and the shared semantic summary/profile/story surfaces report metaclass ownership without any Python fallback. The dedicated `USES_METACLASS` relationship itself is still content-backed rather than a first-class persisted graph edge. |
| Inheritance | `inheritance` | supported | `classes` | `name, line_number, bases` | `relationship:INHERITS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Type annotations | `type-annotations` | partial | `type_annotations` | `name, line_number, type` | `content:TypeAnnotation entity + code/language/entity_context.story` | `go/internal/query/language_queries_test.go::TestHandleLanguageQuery_ContentBackedEntityTypes`, `go/internal/query/entity_content_fallback_test.go::TestResolveEntityFallsBackToContentEntities`, `go/internal/query/content_reader_test.go::TestCodeHandlerSearchEntityContentIncludesEntityNameMatches`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryTypeAnnotation` | Compose-backed fixture verification | Type annotations are queryable through the Go content-backed language-query and content APIs, the normal entity resolve/context surfaces now fall back to content-backed entities, the normal `code/search` fallback now searches content-backed entity names as well as source text, and `language-query`, `code/search`, plus entity-context now emit both a semantic summary and a structured `semantic_profile` for type-annotation entities while entity-context can now also emit a first-class `story`. Dedicated graph-first surfacing remains partial. |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `supported`
- Framework packs: `fastapi-base`, `flask-base`
- Query surfacing: `supported`
- Real-repo validation: `supported`
- End-to-end indexing: `supported`
- Notes:
  - Framework evidence for FastAPI and Flask is carried by the Go parser and
    indexing path.
  - Type annotations are queryable through the Go content-backed APIs, the
    normal entity resolve/context surfaces now fall back to content-backed
    entities, and the normal `code/search` fallback now searches
    content-backed entity names as well as source text. `code/language-query`
    now projects Python decorator, async, lambda, and metaclass metadata
    directly from graph rows, while `code/search`, entity-context, and
    repository stories still rely on the shared enrichment path to surface
    those semantics as summaries, `semantic_profile`, and first-class
    `story` output. Dedicated persisted graph relationships for metaclass
    ownership remain partial.
  - Identifier-assigned lambdas now materialize as Python function entities
    with `semantic_kind=lambda`, and the normal semantic/profile/story
    surfaces promote them as `lambda_function`.
  - Python metaclass ownership is now preserved on class entities, surfaced
    directly on the graph-backed `code/language-query` path, and exposed
    through content-backed `USES_METACLASS` relationships on the normal query
    path.


## Known Limitations
- Inline lambdas that are not bound to a stable identifier remain ordinary
  expressions rather than first-class entities.
