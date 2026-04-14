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
| Type aliases | `type-aliases` | partial | `type_aliases` | `name, line_number` | `content:TypeAlias entity` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXSemanticsAndComponents` | Compose-backed fixture verification | TSX files inherit TypeScript type-alias extraction, and those aliases are materialized as content entities. The remaining gap is first-class normal query surfacing. |
| JSX component usage | `jsx-component-usage` | partial | `function_calls` | `name, line_number` | `content:Entity.metadata + component entities` | `go/internal/parser/engine_javascript_semantics_test.go::TestDefaultEngineParsePathTSXJSXComponentUsageParity` | Compose-backed fixture verification | PascalCase JSX tag usage is captured through the Go TSX parser's call-like semantics, but there is still no dedicated component-reference query contract. |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `supported`
- Framework packs: `react-base`, `nextjs-app-router-base`
- Query surfacing: `partial`
- Real-repo validation: `supported`
- End-to-end indexing: `supported`
- Notes:
  - Real-repo validation covers React and Next.js evidence through the
    Go-owned parser and indexing path.
  - TSX type aliases and JSX evidence survive parse and content
    materialization, while dedicated component/reference query surfacing
    remains partial.


## Known Limitations
- JSX element tag names are not modeled as distinct component reference nodes
- Fragment shorthand (`<>...</>`) is not separately tracked
- TSX-specific type narrowing patterns (e.g., `as ComponentType`) are not captured
