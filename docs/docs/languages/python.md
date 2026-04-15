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
| Decorators | `decorators` | partial | `functions` | `name, line_number, decorators` | `content:Entity.metadata.decorators + code/language/entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonDecoratedFunctionsEmitDecoratorMetadata`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonFunction`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositoryStoryResponseIncludesSemanticOverview` | Compose-backed fixture verification | Decorator metadata is emitted and preserved in content entities, graph-backed query surfaces enrich matching rows with that metadata, and `language-query`, `code/search`, plus entity-context now emit both a first-class semantic summary and a structured `semantic_profile` bundle when decorator metadata is present; entity-context now also emits a first-class `story`, and repository stories now carry a semantic overview derived from those same entities. Broader graph-first modeling remains partial. |
| Async functions | `async-functions` | partial | `functions` | `name, line_number, async` | `content:Entity.metadata.async + code/language/entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonAsyncFunctionsEmitAsyncFlag`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonFunction`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositoryStoryResponseIncludesSemanticOverview` | Compose-backed fixture verification | The async flag is emitted and preserved in content entities, graph-backed query surfaces enrich matching rows with that metadata, and `language-query`, `code/search`, plus entity-context now emit both a first-class semantic summary and a structured `semantic_profile` bundle when async metadata is present; entity-context now also emits a first-class `story`, and repository stories now carry a semantic overview derived from those same entities. Higher-level graph-first modeling remains partial. |
| Metaclass relationships | `metaclass-relationships` | partial | `classes` | `name, line_number, metaclass` | `content:Entity.metadata.metaclass + code/relationships + entity_context.relationships` | `go/internal/parser/engine_python_metaclass_test.go::TestDefaultEngineParsePathPythonEmitsMetaclassMetadata`, `go/internal/query/content_relationships_python_test.go::TestBuildContentRelationshipSetPythonClassUsesMetaclass`, `go/internal/query/content_relationships_python_test.go::TestBuildContentRelationshipSetPythonMetaclassHasIncomingUsage` | Compose-backed fixture verification | Class entities now preserve `metaclass` metadata on the Go parser/content path, and the normal content-backed relationship builder can surface `USES_METACLASS` edges in both directions without any Python fallback. Dedicated graph-first promotion beyond the shared content/query path remains partial. |
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
    content-backed entity names as well as source text. Graph-backed
    `language-query`, `code/search`, `dead-code`, `code/relationships`,
    `code/complexity`, `entities/resolve`, and entity-context results now
    enrich matching rows with decorator and async metadata. `language-query`,
    `code/search`, and entity-context also emit both semantic summaries and a
    structured `semantic_profile` for Python decorator, async, and
    type-annotation semantics, entity-context now also emits a first-class
    `story`, and repository stories now expose a semantic overview derived
    from those same entities. Higher-level graph-first modeling beyond those
    shared query outputs remains partial.
  - Python metaclass ownership is now preserved on class entities and exposed
    through content-backed `USES_METACLASS` relationships on the normal query
    path.


## Known Limitations
- Lambda functions detected as unnamed functions
- Comprehension-internal functions not always tracked
