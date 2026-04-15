# Python Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `python`
- Family: `language`
- Parser: `DefaultEngine (python)`
- Entrypoint: `go/internal/parser/python_language.go`
- Fixture repo: `tests/fixtures/ecosystems/python_comprehensive/`
- Unit test suite: `go/internal/parser/engine_python_semantics_test.go`
- Integration validation: compose-backed fixture verification (see `../reference/local-testing.md`)

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Decorators | `decorators` | partial | `functions` | `name, line_number, decorators` | `content:Entity.metadata.decorators + code/language/entity_context.semantic_profile` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonDecoratedFunctionsEmitDecoratorMetadata`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonFunction` | Compose-backed fixture verification | Decorator metadata is emitted and preserved in content entities, graph-backed query surfaces enrich matching rows with that metadata, and `language-query`, `code/search`, plus entity-context now emit both a first-class semantic summary and a structured `semantic_profile` bundle when decorator metadata is present. Broader graph/story/context surfacing remains partial. |
| Async functions | `async-functions` | partial | `functions` | `name, line_number, async` | `content:Entity.metadata.async + code/language/entity_context.semantic_profile` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonAsyncFunctionsEmitAsyncFlag`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryPythonFunction` | Compose-backed fixture verification | The async flag is emitted and preserved in content entities, graph-backed query surfaces enrich matching rows with that metadata, and `language-query`, `code/search`, plus entity-context now emit both a first-class semantic summary and a structured `semantic_profile` bundle when async metadata is present. Higher-level graph/story/context surfacing remains partial. |
| Inheritance | `inheritance` | supported | `classes` | `name, line_number, bases` | `relationship:INHERITS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | Compose-backed fixture verification | - |
| Type annotations | `type-annotations` | partial | `type_annotations` | `name, line_number, type` | `content:TypeAnnotation entity + code/language/entity_context.semantic_profile` | `go/internal/query/language_queries_test.go::TestHandleLanguageQuery_ContentBackedEntityTypes`, `go/internal/query/entity_content_fallback_test.go::TestResolveEntityFallsBackToContentEntities`, `go/internal/query/content_reader_test.go::TestCodeHandlerSearchEntityContentIncludesEntityNameMatches`, `go/internal/query/entity_summary_test.go::TestBuildEntitySemanticSummaryTypeAnnotation` | Compose-backed fixture verification | Type annotations are queryable through the Go content-backed language-query and content APIs, the normal entity resolve/context surfaces now fall back to content-backed entities, the normal `code/search` fallback now searches content-backed entity names as well as source text, and `language-query`, `code/search`, plus entity-context now emit both a semantic summary and a structured `semantic_profile` for type-annotation entities. Dedicated graph/story surfacing remains partial. |

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
    type-annotation semantics. Higher-level graph/story/context surfacing
    beyond those shared query outputs remains partial.


## Known Limitations
- Lambda functions detected as unnamed functions
- Comprehension-internal functions not always tracked
- Metaclass relationships not captured
