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
| Decorators | `decorators` | partial | `functions` | `name, line_number, decorators` | `graph:code/language-query metadata + graph-first entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonDecoratedFunctionsEmitDecoratorMetadata`, `go/internal/query/language_query_result_test.go::TestBuildLanguageResult_AttachesPythonGraphMetadataAndSemanticSummary`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadataPreservesPythonGraphMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadataPrefersExistingPythonGraphMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonFunction`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/entity_story_test.go::TestGetEntityContextUsesGraphPythonMetadataWithoutContent`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | Decorator metadata is emitted on the Go parser path, persisted on the graph-backed semantic entity row, projected directly by `code/language-query`, and now preserved by graph-first entity-context/story when the graph row already carries metadata. `code/search` and repository stories still use the shared enrichment path where graph data is missing. |
| Async functions | `async-functions` | partial | `functions` | `name, line_number, async` | `graph:code/language-query metadata + graph-first entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonAsyncFunctionsEmitAsyncFlag`, `go/internal/query/language_query_result_test.go::TestBuildLanguageResult_AttachesPythonGraphMetadataAndSemanticSummary`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadataPrefersExistingPythonGraphMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonFunction`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/entity_story_test.go::TestGetEntityContextUsesGraphPythonMetadataWithoutContent`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | The async flag is emitted on the Go parser path, persisted on the graph-backed semantic entity row, projected directly by `code/language-query`, and now preserved by graph-first entity-context/story when the graph row already carries metadata. Broader graph-first modeling beyond the current query/stories layer remains partial. |
| Lambda assignments | `lambda-assignments` | partial | `functions` | `name, line_number, semantic_kind=lambda` | `graph:code/language-query metadata + graph-first entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_python_metaclass_test.go::TestDefaultEngineParsePathPythonLambdaAssignmentEmitsNamedFunction`, `go/internal/query/python_semantics_promotion_test.go::TestPythonSemanticProfileFromMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonLambdaFunction`, `go/internal/query/entity_story_test.go::TestGetEntityContextUsesGraphPythonMetadataWithoutContent`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | Identifier-assigned lambdas materialize as function entities with `semantic_kind=lambda`, are persisted on the graph-backed semantic entity row, and are promoted consistently by the normal semantic/profile/story surfaces without any Python fallback. Inline lambdas that are not bound to a stable identifier remain ordinary expressions rather than first-class entities. |
| Metaclass relationships | `metaclass-relationships` | supported | `classes` | `name, line_number, metaclass` | `graph:code/language-query metadata + graph-first entity_context.story + relationship:USES_METACLASS + code/relationships` | `go/internal/parser/engine_python_metaclass_test.go::TestDefaultEngineParsePathPythonEmitsMetaclassMetadata`, `go/internal/query/language_query_result_test.go::TestBuildLanguageResult_AttachesPythonGraphMetadataAndSemanticSummary`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadataPreservesPythonGraphMetadata`, `go/internal/query/code_relationships_graph_test.go::TestHandleRelationshipsReturnsGraphBackedPythonMetaclassUsesMetaclass`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonMetaclassClass`, `go/internal/query/entity_story_test.go::TestGetEntityContextUsesGraphPythonMetadataWithoutContent`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | Class entities now preserve `metaclass` metadata on the Go parser path, `code/language-query` projects that metadata directly from graph rows, and the normal `code/relationships` path now returns persisted `USES_METACLASS` graph edges without the old content fallback. Graph-backed entity-context/story now also preserves the graph row when metaclass metadata is already present. |
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
  - Python function semantics for decorators, async, and `semantic_kind=lambda`
    are persisted on the graph-backed semantic entity row and projected
    directly by `code/language-query`; graph-backed entity-context/story now
    preserves the graph row when that metadata is already present, and the
    remaining content-backed surfaces still use the shared enrichment path
    where graph data is absent.
  - Type annotations are queryable through the Go content-backed APIs, the
    normal entity resolve/context surfaces now fall back to content-backed
    entities, and the normal `code/search` fallback now searches
    content-backed entity names as well as source text. `code/language-query`
    now projects Python decorator, async, lambda, and metaclass metadata
    directly from graph rows, while `code/search` and repository stories still
    rely on the shared enrichment path to surface those semantics as
    summaries, `semantic_profile`, and first-class `story` output when graph
    data is absent. Python metaclass ownership now persists as a graph-backed
    `USES_METACLASS` relationship on the normal `code/relationships` path,
    and graph-backed entity-context/story now preserves the graph row when
    metaclass metadata is already present.
  - Identifier-assigned lambdas now materialize as Python function entities
    with `semantic_kind=lambda`, and the normal semantic/profile/story
    surfaces promote them as `lambda_function`.
  - Python metaclass ownership is now preserved on class entities, surfaced
    directly on the graph-backed `code/language-query` path, and exposed
    through persisted `USES_METACLASS` relationships on the normal
    `code/relationships` path.


## Known Limitations
- Inline lambdas that are not bound to a stable identifier remain ordinary
  expressions rather than first-class entities.
