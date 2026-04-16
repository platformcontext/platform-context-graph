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
| Decorators | `decorators` | partial | `functions` | `name, line_number, decorators` | `graph:code/language-query metadata + first-class python_semantics bundle + graph-first entity_context.story + entities/resolve + code/search` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonDecoratedFunctionsEmitDecoratorMetadata`, `go/internal/query/language_query_result_test.go::TestBuildLanguageResult_AttachesPythonGraphMetadataAndSemanticSummary`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadataPreservesPythonGraphMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestHandleSearchReturnsGraphBackedPythonDecoratedClassWithoutContent`, `go/internal/query/entity_content_fallback_test.go::TestResolveEntityReturnsGraphBackedPythonDecoratedClassWithPythonSemantics`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadataPrefersExistingPythonGraphMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonFunction`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonDecoratedClass`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/entity_story_test.go::TestGetEntityContextUsesGraphPythonMetadataWithoutContent`, `go/internal/query/entity_story_test.go::TestGetEntityContextUsesGraphPythonDecoratedClassWithoutContent`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | Decorator metadata is emitted on the Go parser path, persisted on the graph-backed semantic entity row, projected directly by `code/language-query`, and now preserved by graph-first entity-context/story, `entities/resolve`, and `code/search` when the graph row already carries metadata. Python class rows now surface as `decorated_class` on the normal graph-backed query and search paths, while decorated async functions remain `decorated_async_function`. Graph-backed Python query/search/context/resolve responses also carry a dedicated `python_semantics` bundle for structured consumers. `repository_story` still uses the shared enrichment path where graph data is missing. |
| Async functions | `async-functions` | partial | `functions` | `name, line_number, async` | `graph:code/language-query metadata + graph-first entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonAsyncFunctionsEmitAsyncFlag`, `go/internal/query/language_query_result_test.go::TestBuildLanguageResult_AttachesPythonGraphMetadataAndSemanticSummary`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadataPrefersExistingPythonGraphMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonFunction`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/entity_story_test.go::TestGetEntityContextUsesGraphPythonMetadataWithoutContent`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | The async flag is emitted on the Go parser path, persisted on the graph-backed semantic entity row, projected directly by `code/language-query`, and now preserved by graph-first entity-context/story when the graph row already carries metadata. Broader graph-first modeling beyond the current query/stories layer remains partial. |
| Lambda assignments | `lambda-assignments` | partial | `functions` | `name, line_number, semantic_kind=lambda` | `graph:code/language-query metadata + graph-first entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_python_metaclass_test.go::TestDefaultEngineParsePathPythonLambdaAssignmentEmitsNamedFunction`, `go/internal/query/python_semantics_promotion_test.go::TestPythonSemanticProfileFromMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonLambdaFunction`, `go/internal/query/entity_story_test.go::TestGetEntityContextUsesGraphPythonMetadataWithoutContent`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | Identifier-assigned lambdas materialize as function entities with `semantic_kind=lambda`, are persisted on the graph-backed semantic entity row, and are promoted consistently by the normal semantic/profile/story surfaces without any Python fallback. Inline lambdas that are not bound to a stable identifier remain ordinary expressions rather than first-class entities. |
| Metaclass relationships | `metaclass-relationships` | supported | `classes` | `name, line_number, metaclass` | `graph:code/language-query metadata + graph-first entity_context.story + relationship:USES_METACLASS + code/relationships` | `go/internal/parser/engine_python_metaclass_test.go::TestDefaultEngineParsePathPythonEmitsMetaclassMetadata`, `go/internal/query/language_query_result_test.go::TestBuildLanguageResult_AttachesPythonGraphMetadataAndSemanticSummary`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadataPreservesPythonGraphMetadata`, `go/internal/query/code_relationships_graph_test.go::TestHandleRelationshipsReturnsGraphBackedPythonMetaclassUsesMetaclass`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonMetaclassClass`, `go/internal/query/entity_story_test.go::TestGetEntityContextUsesGraphPythonMetadataWithoutContent`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositorySemanticOverviewCountsSemanticSignals` | Compose-backed fixture verification | Class entities now preserve `metaclass` metadata on the Go parser path, `code/language-query` projects that metadata directly from graph rows, and the normal `code/relationships` path now returns persisted `USES_METACLASS` graph edges without the old content fallback. Graph-backed entity-context/story now also preserves the graph row when metaclass metadata is already present. |
| Inheritance | `inheritance` | supported | `classes` | `name, line_number, bases` | `relationship:INHERITS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Type annotations | `type-annotations` | partial | `type_annotations` | `name, line_number, type` | `graph:first-class TypeAnnotation entity + graph-backed function annotation projection + code/language/entity_context.story` | `go/internal/query/language_queries_test.go::TestHandleLanguageQuery_ContentBackedEntityTypes`, `go/internal/query/language_query_result_test.go::TestBuildLanguageResult_AttachesPythonTypeAnnotationGraphMetadata`, `go/internal/query/language_query_result_test.go::TestBuildLanguageResult_AttachesPythonTypeAnnotationProjection`, `go/internal/query/entity_content_fallback_test.go::TestResolveEntityFallsBackToContentEntities`, `go/internal/query/content_reader_test.go::TestCodeHandlerSearchEntityContentIncludesEntityNameMatches`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryTypeAnnotation`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryTypeAnnotationReturn`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonFunctionTypeAnnotations`, `go/internal/query/entity_story_test.go::TestGetEntityContextUsesGraphPythonTypeAnnotationWithoutContent`, `go/internal/query/entity_story_test.go::TestGetEntityContextUsesGraphPythonTypeAnnotationsWithoutContent`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/python_semantics_promotion_test.go::TestPythonSemanticProfileFromMetadata` | Compose-backed fixture verification | Type annotations now materialize as first-class graph-backed `TypeAnnotation` entities when the graph row exists. Function rows also retain a compact `type_annotation_count`/`type_annotation_kinds` projection on the graph-backed path so normal language-query, code/search, and entity-context surfaces can keep Python annotation signal graph-first even when the richer parser fact is no longer in the content fallback. Legacy content-backed fallback remains only for rows that are not yet materialized in the graph. |

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
    directly by `code/language-query`; graph-backed entity-context/story and
    `code/search` now preserve the graph row when that metadata is already
    present, including Python class rows that surface as `decorated_class`,
    and the remaining content-backed surfaces still use the shared enrichment
    path where graph data is absent.
  - Python type-annotation signal now also survives as a compact
    `type_annotation_count`/`type_annotation_kinds` projection on graph-backed
    function rows, so the normal query surfaces do not lose annotation signal
    after materialization even though Neo4j cannot store the parser's full
    annotation maps.
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
  - Graph-backed Python metadata is now also preserved on the entity-ID
    enrichment path used by `code/dead-code` and `code/complexity`, so those
    responses keep graph-owned decorators, async flags, and annotation signals
    when content fallback is available for the same entity.
  - Graph-backed Python docstrings now keep a Python-specific documented
    surface kind in `semantic_profile` and related story/context responses:
    classes surface as `documented_class`, functions as
    `documented_function`, and the generic `documented_entity` fallback is
    reserved for non-Python or unlabeled content.
  - Graph-backed Python query/search/context/story responses also expose a
    dedicated `python_semantics` bundle for structured consumers alongside
    `semantic_profile`; that bundle now carries the promoted `surface_kind`
    and ordered `signals` for graph-backed Python rows as well as the raw
    decorator, async, lambda, metaclass, and type-annotation fields.
  - Identifier-assigned lambdas now materialize as Python function entities
    with `semantic_kind=lambda`, and the normal semantic/profile/story
    surfaces promote them as `lambda_function` and describe them as lambda
    functions.
  - Graph-backed Python decorator rows are also preserved by the normal
    `entities/resolve` surface, which now returns the same structured
    `python_semantics` bundle and `decorated_class` surface kind when the
    graph row already carries decorator metadata.
  - Python metaclass ownership is now preserved on class entities, surfaced
    directly on the graph-backed `code/language-query` path, and exposed
    through persisted `USES_METACLASS` relationships on the normal
    `code/relationships` path.


## Known Limitations
- Inline lambdas that are not bound to a stable identifier remain ordinary
  expressions rather than first-class entities.
