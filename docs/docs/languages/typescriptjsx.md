# TypeScript JSX Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `typescriptjsx`
- Family: `language`
- Parser: `DefaultEngine (tsx)`
- Entrypoint: `go/internal/parser/javascript_language.go`
- Fixture repo: `tests/fixtures/ecosystems/tsx_comprehensive/`
- Unit test suite: `go/internal/parser/engine_javascript_semantics_test.go`
- Integration validation: compose-backed fixture verification (see `../reference/local-testing.md`)

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXClassComponentParity` | Compose-backed fixture verification | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXSemanticsAndComponents` | Compose-backed fixture verification | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXSemanticsAndComponents` | Compose-backed fixture verification | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXSemanticsAndComponents` | Compose-backed fixture verification | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXJSXComponentUsageParity` | Compose-backed fixture verification | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXSemanticsAndComponents` | Compose-backed fixture verification | - |
| Type aliases | `type-aliases` | supported | `type_aliases` | `name, line_number` | `node:TypeAlias + graph-first code/language-query + entity_context.story` | `go/internal/query/language_query_graph_first_test.go::TestHandleLanguageQuery_TypeAliasPrefersGraphPathAndUsesGraphMetadataWithoutContent`, `go/internal/projector/runtime_test.go::TestRuntimeProjectEnqueuesSemanticEntityMaterializationForAnnotationTypedefTypeAliasAndComponent`, `go/internal/reducer/semantic_entity_materialization_test.go::TestExtractSemanticEntityRowsFiltersAnnotationTypedefTypeAliasAndComponentFacts`, `go/internal/storage/neo4j/semantic_entity_test.go::TestSemanticEntityWriterWritesAnnotationTypedefTypeAliasAndComponentNodes`, `go/internal/query/language_query_alias_test.go::TestBuildLanguageCypher_TSXUsesTypeScriptExtensions`, `go/internal/query/entity_content_fallback_test.go::TestResolveEntityFallsBackToContentEntities`, `go/internal/query/content_reader_test.go::TestCodeHandlerSearchEntityContentIncludesEntityNameMatches` | Compose-backed fixture verification | TSX files inherit TypeScript type-alias extraction, those aliases now persist as first-class `TypeAlias` graph nodes through the Go projector/reducer/Neo4j path, the normal `code/language-query` surface prefers graph rows before falling back to content, and entity resolve/context plus `code/search` still preserve the fallback path when the graph is empty. |
| JSX component usage | `jsx-component-usage` | supported | `function_calls` | `name, line_number` | `node:Component + canonical TSX REFERENCES edges + semantic_profile + story` | `go/internal/query/language_query_graph_first_test.go::TestHandleLanguageQuery_TSXComponentUsesGraphMetadataWithoutContent`, `go/internal/query/language_query_tsx_component_graph_first_test.go::TestHandleLanguageQuery_TSXComponentUsesGraphFirstPath`, `go/internal/projector/runtime_test.go::TestRuntimeProjectEnqueuesSemanticEntityMaterializationForAnnotationTypedefTypeAliasAndComponent`, `go/internal/reducer/semantic_entity_materialization_test.go::TestExtractSemanticEntityRowsFiltersAnnotationTypedefTypeAliasAndComponentFacts`, `go/internal/storage/neo4j/semantic_entity_test.go::TestSemanticEntityWriterWritesAnnotationTypedefTypeAliasAndComponentNodes`, `go/internal/query/code_relationships_graph_test.go::TestHandleRelationshipsReturnsGraphBackedTSXComponentReferences`, `go/internal/query/code_relationships_graph_test.go::TestHandleRelationshipsNormalizesGraphBackedTSXComponentCalls`, `go/internal/query/entity_content_fallback_test.go::TestGetEntityContextFallsBackToContentEntities`, `go/internal/query/content_reader_test.go::TestCodeHandlerSearchEntityContentIncludesEntityNameMatches`, `go/internal/query/entity_story_test.go::TestGetEntityContextFallsBackToContentEntitiesIncludesStory`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositoryStoryResponseIncludesSemanticOverview` | Compose-backed fixture verification | PascalCase JSX tag usage now routes through first-class persisted `Component` graph nodes, canonical Neo4j writes persist JSX component usage as `REFERENCES` edges, `code/language-query` accepts direct `tsx` requests, the query layer still normalizes older graph-backed `CALLS` edges with `call_kind=jsx_component` for compatibility, and the empty-graph fallback path still uses content-backed component entities. |
| JSX fragment shorthand | `jsx-fragment-shorthand` | partial | `functions, components` | `name, line_number, jsx_fragment_shorthand=true` | `graph-backed language-query metadata + content-backed search/context/story surfaces` | `go/internal/parser/engine_tsx_advanced_semantics_test.go::TestDefaultEngineParsePathTSXCapturesFragmentAndComponentTypeAssertion`, `go/internal/query/language_query_graph_first_test.go::TestHandleLanguageQuery_TSXFunctionFragmentUsesGraphMetadataWithoutContent`, `go/internal/query/entity_metadata_tsx_semantics_test.go::TestEnrichEntityResultsWithContentMetadataTSXFragmentComponent`, `go/internal/query/repository_story_tsx_semantics_test.go::TestBuildRepositorySemanticOverviewCountsTSXAdvancedSignals` | Compose-backed fixture verification | The Go parser preserves fragment shorthand usage on TSX function and component entities, the normal query/context/story surfaces promote that metadata into semantic summaries, structured semantic profiles, and repository-story semantic counts, and the shared graph-backed `language-query` path now also understands fragment metadata when matching graph rows already carry it. First-class graph persistence remains partial. |
| ComponentType narrowing | `component-type-narrowing` | partial | `variables` | `name, line_number, component_type_assertion` | `graph-backed language-query metadata + content-backed search/context/story surfaces` | `go/internal/parser/engine_tsx_advanced_semantics_test.go::TestDefaultEngineParsePathTSXCapturesFragmentAndComponentTypeAssertion`, `go/internal/query/language_query_graph_first_test.go::TestHandleLanguageQuery_TSXVariableAssertionUsesGraphMetadataWithoutContent`, `go/internal/query/entity_metadata_tsx_semantics_test.go::TestEnrichEntityResultsWithContentMetadataTSXComponentTypeAssertion`, `go/internal/query/repository_story_tsx_semantics_test.go::TestBuildRepositorySemanticOverviewCountsTSXAdvancedSignals` | Compose-backed fixture verification | TSX `as ComponentType<...>` narrowing now survives on the Go parser/content/query path through variable metadata and semantic promotion, and the shared graph-backed `language-query` path now also understands that narrowing metadata when matching graph rows already carry it. First-class graph persistence remains partial. |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `supported`
- Framework packs: `react-base`, `nextjs-app-router-base`
- Query surfacing: `supported`
- Real-repo validation: `supported`
- End-to-end indexing: `supported`
- Notes:
  - Real-repo validation covers React and Next.js evidence through the
    Go-owned parser and indexing path.
  - TSX type aliases now persist as first-class `TypeAlias` graph nodes and
    TSX components now persist as first-class `Component` graph nodes through
    the Go projector/reducer/Neo4j path. Normal `code/language-query` accepts
    direct `tsx` requests, prefers graph-backed `TypeAlias` and `Component`
    rows when they exist, and still falls back to content-backed entities when
    the graph is empty. Normal entity resolve/context can still surface
    content-backed entities, normal `code/search` can still search entity
    names as well as source text and emit both semantic summaries and a
    structured `semantic_profile` for matching component entities, fragment
    shorthand and `as ComponentType<...>` narrowing now also surface through
    semantic summaries, structured `semantic_profile` payloads, and
    repository-story semantic counts, entity-context now also emits a
    first-class `story`, repository stories now expose a semantic overview
    derived from those same entities, and normal `code/relationships` can
    still synthesize JSX component-reference edges for content-backed
    entities when direct graph edges are absent.


## Known Limitations
- Fragment shorthand now has content-backed semantic parity, but first-class
  graph persistence is still partial
- TSX-specific type narrowing patterns such as `as ComponentType<...>` now have
  content-backed semantic parity, but first-class graph persistence is still
  partial
- JSX component-reference edges now persist as first-class graph
  `REFERENCES` edges during normal Go writes; the query layer still
  normalizes older `CALLS` edges with `call_kind=jsx_component`, and content
  metadata still backs the empty-graph fallback path
