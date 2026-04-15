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
| Type aliases | `type-aliases` | partial | `type_aliases` | `name, line_number` | `content:TypeAlias entity + code/language/entity_context.story` | `go/internal/query/language_queries_test.go::TestHandleLanguageQuery_ContentBackedEntityTypes`, `go/internal/query/language_query_alias_test.go::TestBuildLanguageCypher_TSXUsesTypeScriptExtensions`, `go/internal/query/entity_content_fallback_test.go::TestResolveEntityFallsBackToContentEntities`, `go/internal/query/content_reader_test.go::TestCodeHandlerSearchEntityContentIncludesEntityNameMatches` | Compose-backed fixture verification | TSX files inherit TypeScript type-alias extraction, those aliases are queryable through the Go content-backed language-query and content APIs, the normal entity resolve/context surfaces now also fall back to content-backed entities, `code/language-query` now also accepts direct `tsx` requests, the normal `code/search` fallback now searches content-backed entity names as well as source text, and entity-context can now emit a first-class `story` for matching semantic entities. The remaining gap is dedicated graph-first modeling beyond the shared query/story surfaces. |
| JSX component usage | `jsx-component-usage` | partial | `function_calls` | `name, line_number` | `content:Entity.metadata + component entities + synthesized REFERENCES edges + semantic_profile + story` | `go/internal/query/language_queries_test.go::TestHandleLanguageQuery_ContentBackedEntityTypes`, `go/internal/query/language_query_alias_test.go::TestSupportedLanguages_ExplicitJSXAndTSX`, `go/internal/query/language_query_alias_test.go::TestBuildLanguageCypher_TSXUsesTypeScriptExtensions`, `go/internal/query/entity_content_fallback_test.go::TestGetEntityContextFallsBackToContentEntities`, `go/internal/query/code_relationships_content_fallback_test.go::TestHandleRelationshipsFallsBackToContentEntityReferences`, `go/internal/query/content_reader_test.go::TestCodeHandlerSearchEntityContentIncludesEntityNameMatches`, `go/internal/query/entity_story_test.go::TestGetEntityContextFallsBackToContentEntitiesIncludesStory`, `go/internal/query/repository_story_semantics_test.go::TestBuildRepositoryStoryResponseIncludesSemanticOverview` | Compose-backed fixture verification | PascalCase JSX tag usage is queryable through the Go content-backed `component` contract, `code/language-query` now also accepts direct `tsx` requests, content-backed component entities now participate in the normal entity context surface, the normal `code/relationships` surface now synthesizes `REFERENCES` edges from `jsx_component_usage` metadata, shared query surfaces now emit a structured `semantic_profile`, entity-context now also emits a first-class `story`, and repository stories now carry a semantic overview derived from those same entities. Full graph-first component/reference modeling remains partial. |

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
  - TSX type aliases and JSX evidence are queryable through the Go
    content-backed APIs, normal `code/language-query` now also accepts
    direct `tsx` requests, normal entity resolve/context can surface
    content-backed entities, normal `code/search` can now search
    content-backed entity names as well as source text and emit both semantic
    summaries and a structured `semantic_profile` for content-backed
    component entities, entity-context now also emits a first-class `story`,
    repository stories now expose a semantic overview derived from those same
    entities, and normal `code/relationships` can synthesize JSX
    component-reference edges for content-backed entities. Full graph-first
    component/reference surfacing remains partial.


## Known Limitations
- JSX element tag names are not yet persisted as first-class graph nodes
- Fragment shorthand (`<>...</>`) is not separately tracked
- TSX-specific type narrowing patterns (e.g., `as ComponentType`) are not captured
