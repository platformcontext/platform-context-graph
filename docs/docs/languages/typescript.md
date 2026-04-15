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
| Type aliases | `type-aliases` | supported | `type_aliases` | `name, line_number` | `node:TypeAlias + graph-first code/language-query + entity_context.story` | `go/internal/query/language_query_graph_first_test.go::TestHandleLanguageQuery_TypeAliasPrefersGraphPathAndUsesGraphMetadataWithoutContent`, `go/internal/projector/runtime_test.go::TestRuntimeProjectEnqueuesSemanticEntityMaterializationForAnnotationTypedefTypeAliasAndComponent`, `go/internal/reducer/semantic_entity_materialization_test.go::TestExtractSemanticEntityRowsFiltersAnnotationTypedefTypeAliasAndComponentFacts`, `go/internal/storage/neo4j/semantic_entity_test.go::TestSemanticEntityWriterWritesAnnotationTypedefTypeAliasAndComponentNodes`, `go/internal/query/entity_content_fallback_test.go::TestResolveEntityFallsBackToContentEntities`, `go/internal/query/content_reader_test.go::TestCodeHandlerSearchEntityContentIncludesEntityNameMatches` | Compose-backed fixture verification | Type aliases now persist as first-class `TypeAlias` graph nodes through the Go projector/reducer/Neo4j path, the normal `code/language-query` surface prefers graph rows before falling back to content, and normal entity resolve/context plus `code/search` still preserve the fallback path when the graph is empty. |
| Decorators | `decorators` | partial | `classes` | `name, line_number` | `content:Entity.metadata.decorators + code/language/entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTypeScriptDecoratorAndGenericParity`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositoryStoryResponseIncludesSemanticOverview` | Compose-backed fixture verification | Decorator metadata is emitted and preserved in content entities, and graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context responses now enrich matching rows with that metadata while also emitting a structured `semantic_profile`; entity-context now also emits a first-class `story`, and repository stories now carry a semantic overview derived from those same entities. What remains partial is dedicated graph-first modeling beyond the shared query/story surfaces. |
| Generics | `generics` | partial | `type_parameters` | `name, line_number, type_parameters` | `content:Entity.metadata.type_parameters + code/language/entity_context.story + repository_story.semantic_overview` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTypeScriptDecoratorAndGenericParity`, `go/internal/query/language_query_metadata_test.go::TestEnrichLanguageResultsWithContentMetadata`, `go/internal/query/code_search_metadata_test.go::TestEnrichGraphSearchResultsWithContentMetadata`, `go/internal/query/entity_metadata_test.go::TestEnrichEntityResultsWithContentMetadata`, `go/internal/query/entity_story_test.go::TestAttachSemanticSummaryAddsStoryForSemanticEntities`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositoryStoryResponseIncludesSemanticOverview` | Compose-backed fixture verification | Type parameter metadata is preserved in content entities and can now flow into graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context responses for matching entities, including a structured `semantic_profile`; entity-context now also emits a first-class `story`, and repository stories now carry a semantic overview derived from those same entities. What remains partial is dedicated graph-first modeling beyond the shared query/story surfaces. |
| Mapped types | `mapped-types` | partial | `type_aliases` | `name, line_number, type_alias_kind=mapped_type` | `content:TypeAlias.metadata.type_alias_kind + semantic_summary + semantic_profile + repository_story.semantic_overview` | `go/internal/parser/engine_typescript_advanced_semantics_test.go::TestDefaultEngineParsePathTypeScriptCapturesAdvancedTypeSemantics`, `go/internal/query/entity_metadata_typescript_semantics_test.go::TestEnrichEntityResultsWithContentMetadataTypeScriptMappedTypeAlias`, `go/internal/query/repository_story_typescript_semantics_test.go::TestBuildRepositorySemanticOverviewCountsTypeScriptAdvancedSignals` | Compose-backed fixture verification | The Go parser now tags mapped type aliases directly, and the normal query/context/story surfaces promote that metadata into semantic summaries, structured semantic profiles, and repository-story semantic counts. First-class graph persistence remains partial. |
| Conditional types | `conditional-types` | partial | `type_aliases` | `name, line_number, type_alias_kind=conditional_type` | `content:TypeAlias.metadata.type_alias_kind + semantic_summary + semantic_profile + repository_story.semantic_overview` | `go/internal/parser/engine_typescript_advanced_semantics_test.go::TestDefaultEngineParsePathTypeScriptCapturesAdvancedTypeSemantics`, `go/internal/query/repository_story_typescript_semantics_test.go::TestBuildRepositorySemanticOverviewCountsTypeScriptAdvancedSignals` | Compose-backed fixture verification | Conditional type aliases now survive on the Go parser/content/query path with dedicated semantic promotion. First-class graph persistence remains partial. |
| Namespaces | `namespaces` | partial | `modules` | `name, line_number, module_kind=namespace` | `graph-backed language-query metadata + content-backed search/context/story surfaces` | `go/internal/parser/engine_typescript_advanced_semantics_test.go::TestDefaultEngineParsePathTypeScriptCapturesAdvancedTypeSemantics`, `go/internal/query/language_query_graph_first_test.go::TestHandleLanguageQuery_TypeScriptNamespaceUsesGraphMetadataWithoutContent`, `go/internal/query/entity_metadata_typescript_semantics_test.go::TestEnrichEntityResultsWithContentMetadataTypeScriptNamespaceModule`, `go/internal/query/repository_story_typescript_semantics_test.go::TestBuildRepositorySemanticOverviewCountsTypeScriptAdvancedSignals` | Compose-backed fixture verification | TypeScript namespace declarations now materialize as `Module` entities with namespace semantics on the normal Go content/query path, and the shared graph-backed `language-query` path can now summarize namespace rows directly when the graph already carries `module_kind`. Dedicated graph persistence beyond that shared query surface remains partial. |
| Declaration merging | `declaration-merging` | partial | `functions`, `classes`, `interfaces`, `modules`, `enums` | `name, declaration_merge_group, declaration_merge_count, declaration_merge_kinds` | `graph-backed language-query metadata + content-backed search/context/story surfaces` | `go/internal/parser/engine_typescript_advanced_semantics_test.go::TestDefaultEngineParsePathTypeScriptCapturesDeclarationMerging`, `go/internal/query/language_query_graph_first_test.go::TestHandleLanguageQuery_TypeScriptDeclarationMergeUsesGraphMetadataWithoutContent`, `go/internal/query/entity_metadata_typescript_semantics_test.go::TestEnrichEntityResultsWithContentMetadataTypeScriptDeclarationMerging`, `go/internal/query/repository_story_typescript_semantics_test.go::TestBuildRepositorySemanticOverviewCountsTypeScriptAdvancedSignals` | Compose-backed fixture verification | Same-file TypeScript declaration merging between supported declarations now survives the Go parser, is surfaced through semantic summaries, profiles, and stories on the normal content/query path, and is now also projected by the shared graph-backed `language-query` path when matching graph rows already carry the merge metadata. First-class graph persistence remains partial. |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `supported`
- Framework packs: `react-base`, `nextjs-app-router-base`, `express-base`, `hapi-base`, `aws-sdk-base`, `gcp-sdk-base`
- Query surfacing: `supported`
- Real-repo validation: `supported`
- End-to-end indexing: `supported`
- Notes:
  - Real-repo validation covers pure TypeScript repositories without requiring
    TSX-specific framework evidence.
  - TypeScript participates in the same declarative Node HTTP and provider-pack
    program as JavaScript.
  - Type aliases now persist as first-class `TypeAlias` graph nodes through
    the Go projector/reducer/Neo4j path, the normal `code/language-query`
    surface prefers graph rows before falling back to content, the normal
    entity resolve/context surfaces still fall back to content-backed entities,
    and the normal `code/search` fallback still searches entity names as well
    as source text. Mapped types, conditional types, and namespace
    declarations now also carry dedicated semantic metadata through the
    normal Go parser/content/query/story path. Graph-backed `language-query`,
    `code/search`, `dead-code`, `code/relationships`, `code/complexity`,
    `entities/resolve`, and entity-context results also enrich matching
    class/function rows with decorator and generic metadata, and
    `language-query`, `code/search`, plus entity-context now emit both
    semantic summaries and a structured `semantic_profile` for matching
    graph-backed entities. Entity-context now also emits a first-class
    `story`, and repository stories now expose a semantic overview derived
    from those same entities. Dedicated graph-first modeling remains
    partial.


## Known Limitations
- Mapped types and conditional types now have content-backed semantic parity,
  but first-class graph persistence is still partial
- Namespace declarations now materialize as modules on the normal Go path, but
  first-class graph persistence is still partial
- Same-file declaration merging is tracked on the Go content/query/story path,
  but first-class graph persistence is still partial
