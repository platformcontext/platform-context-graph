# Parity Closure Matrix

This matrix turns the parity audit into an execution-grade checklist.

Use this page when deciding whether a workstream is ready to split, implement,
or declare complete. A row only moves to `pass` when the Go platform matches
the old Python platform feature for feature for that surface.

## Status Legend

| Status | Meaning |
| --- | --- |
| `pass` | Go-owned and parity-complete |
| `partial` | Go-owned, but feature or operator parity is still incomplete |
| `fail` | required parity behavior is still missing |
| `bounded` | intentionally narrower than Python and must stay documented as a non-goal |

## Branch Baseline

| Workstream | Status | Current truth | Approval bar |
| --- | --- | --- | --- |
| Runtime ownership | `pass` | Long-running and one-shot services are Go-owned end to end | keep Go-only ownership intact |
| Deployment ownership | `pass` | Dockerfile, Compose, and Helm run the Go platform | keep docs and validation aligned |
| Python normal-path ownership | `pass` | No normal-path Python runtime code remains | do not reintroduce mixed-runtime ownership |
| Feature-for-feature parity | `partial` | Multiple parser, graph, query, and operator gaps remain | close all rows below or explicitly bound them |

## Operator And Runtime Contract Matrix

| Workstream | Status | Gap now | Done means | Validation gate | Recommended split |
| --- | --- | --- | --- | --- | --- |
| `pcg serve start` contract | `partial` | Command still implies API plus MCP together while MCP is separate | command behavior and docs agree exactly | focused Go CLI tests, docs check | standalone small slice |
| API admin route mounting | `partial` | Go admin handlers exist but are not fully exposed through shipped API wiring | admin routes are either fully mounted or fully removed from contract/docs | `go test` for `go/cmd/api` and `go/internal/query`, OpenAPI diff | standalone small slice |
| Status endpoint breadth | `partial` | Current status surface is narrower than parts of the historical operator model | final status surface is intentional, documented, and tested | query/status tests plus compose proof | pair with admin route slice |
| Run-scoped coverage endpoints | `partial` | Docs mention routes that generated OpenAPI does not expose | endpoints exist and are tested, or they are removed from docs | OpenAPI verification, docs build | pair with API/admin slice |
| CLI behavior breadth | `partial` | Some Go CLI flows are thinner than old Python UX | required historical flows are intentionally matched or intentionally retired | focused `go/cmd/pcg` tests and smoke checks | small follow-on slice |

## Parser And Graph-Surface Matrix

| Workstream | Status | Gap now | Done means | Validation gate | Recommended split |
| --- | --- | --- | --- | --- | --- |
| SQL core parsing | `partial` | Mostly complete, with checked-in proof for `CREATE OR REPLACE FUNCTION` bodies and legacy `EXECUTE PROCEDURE` trigger wiring, but some procedural SQL and DDL edges may still remain | no documented SQL-core parity gaps remain | focused parser tests | fold into SQL/dbt wave |
| SQL/dbt lineage | `fail` | dbt compiled lineage still loses unresolved refs, templated expressions, complex macro expansion, and richer derived expressions outside the safe wrapper set, even though the safe-wrapper transform matrix now has checked-in Go proof | compiled dbt lineage survives parse, materialization, and query proof | parser tests, real-repo proof, compose proof | dedicated medium/large wave |
| Canonical code-call materialization | `partial` | the collector and reducer now own canonical `CALLS` edge writes for SCIP-backed parser facts plus generic `function_calls`, including repo-scoped retraction and rewrite during normal Go ingestion. Primary non-SCIP families now preserve richer generic call metadata (`full_name`, JSX/function kind where available, receiver type where available), and the reducer now proves safe same-file plus cross-file matching for JS/TS/TSX import-driven calls and exact-qualified Swift/Ruby/Elixir/PHP static-style calls. The remaining gap is Python cross-file generic call ownership plus parser-first bare-name families that still lack truthful cross-file callee identity | required language families persist canonical call edges through parser, collector, reducer, and query proof without Python fallback | parser tests, reducer/collector tests, query proof | pair with parser-family waves |
| JavaScript graph parity | `partial` | docstrings and method-kind metadata are extracted and materialized, graph-backed query surfaces enrich matching rows with that metadata, and entity-context now emits semantic summaries for matching JavaScript entities, but broader graph/story/context surfacing remains partial | JS docstrings and method metadata persist and query correctly across parser, content, and normal query/context surfaces | parser tests plus query proof | shared JS-family wave |
| TypeScript graph parity | `partial` | decorator and generic metadata are preserved, type aliases are already queryable through Go content-backed APIs, content-backed entities now participate in normal entity resolve/context, the normal `code/search` fallback can now search content-backed entity names as well as source text, and graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context results now enrich matching rows with metadata, but dedicated graph/story/context surfacing remains partial | those semantics persist and query correctly across parser, content, and normal query surfaces | parser tests, graph tests, API/MCP proof | shared JS-family wave |
| TSX graph parity | `partial` | JSX tag usage is captured, type aliases plus component semantics are queryable through Go content-backed APIs, content-backed entities now participate in normal entity resolve/context, the normal `code/search` fallback can now search content-backed entity names as well as source text, and normal `code/relationships` can synthesize JSX component `REFERENCES` edges for content-backed entities, but full graph-first component/reference and higher-level surfacing remain partial | JSX component semantics become first-class across parser, content, relationships, and story/query surfaces | parser tests, graph tests, API/MCP proof | shared JS-family wave |
| Python graph parity | `partial` | decorators and async flags are extracted and materialized, type annotations are already queryable through Go content-backed APIs, content-backed entities now participate in normal entity resolve/context, the normal `code/search` fallback can now search content-backed entity names as well as source text, graph-backed query surfaces enrich matching rows with metadata, and entity-context now emits semantic summaries for Python decorator/async/type-annotation semantics, but broader graph/story/context surfacing remains partial | those semantics persist and query correctly across parser, content, and normal query/context surfaces | parser tests, graph tests, API/MCP proof | parallel medium wave |
| Java graph parity | `partial` | applied annotation usage is now queryable through content-backed `Annotation` entities, but it is still not first-class on the graph/story surfaces | annotations persist and query correctly across parser, content, and normal query surfaces | parser tests plus query proof | long-tail wave |
| Kotlin graph parity | `partial` | secondary constructor metadata now reaches normal query/context semantic summaries, but it is still not first-class on the graph/story surfaces | constructors persist and query correctly across parser, content enrichment, and normal query surfaces | parser tests plus query proof | long-tail wave |
| PHP graph parity | `partial` | reducer-owned PHP call materialization now proves same-file plus cross-file static-style calls and still fails closed for receiver-qualified object calls without inferred type; broader object-call parity is not yet proven end to end | static and object call edges are persisted and queryable with proof | parser tests plus end-to-end proof | long-tail wave |
| C graph parity | `partial` | typedefs are queryable through the Go content-backed language-query surface and now emit semantic summaries in normal query/context responses, but they are not first-class graph entities yet | typedef semantics persist, query correctly, and become graph-first where parity requires it | parser tests plus query proof | long-tail wave |
| Rust graph parity | `partial` | impl blocks now persist as `ImplBlock` content entities and are queryable through `code/language-query`, but implementation edges are still not first-class on the graph | impl ownership and relationships persist and query correctly | parser tests plus query proof | long-tail wave |
| Elixir graph parity | `partial` | guards, protocols, implementations, and module attributes now surface in semantic summaries on normal query/context responses, and reducer-owned same-file plus cross-file call materialization now stays exact-only for qualified Elixir call metadata, but those semantics are still flattened into generic module/function/variable records on the graph | those semantics persist and query correctly | parser tests plus query proof | long-tail wave |

## IaC And Deployment Semantics Matrix

| Workstream | Status | Gap now | Done means | Validation gate | Recommended split |
| --- | --- | --- | --- | --- | --- |
| Terraform parity | `fail` | `terraform {}` metadata and some cross-file semantics are still incomplete | Terraform structural metadata is first-class where Python exposed it | parser tests, relationship tests, query proof | shared HCL wave |
| Terragrunt parity | `partial` | core parsing is Go-owned and dependency/local/input entities are now queryable, but the historical module-source relationship path from `terraform.source` is still missing on the normal graph surface | Terragrunt preserves its current Go-owned entities and restores the historical module-source relationship parity the Python platform exposed | parser tests, query proof, relationship tests | shared HCL wave |
| Kubernetes parity | `fail` | labels and richer resource normalization are incomplete | labels and required resource semantics survive graph/query layers | parser tests plus compose-backed proof | shared YAML/IaC wave |
| ArgoCD parity | `fail` | sync policy and richer generator normalization are incomplete | sync policy and required generator semantics persist and query correctly | parser tests plus compose-backed proof | shared YAML/IaC wave |
| CloudFormation parity | `partial` | YAML and JSON templates now share the same parser materialization, including `file_format`, and the JSON proof is checked in; nested stack references and condition handling remain broader follow-on work | JSON templates reach the same materialization and proof bar as YAML | parser tests plus end-to-end proof | shared YAML/IaC wave |
| Kustomize parity | `partial` | base references are not first-class | base references persist and query correctly | parser tests plus query proof | shared YAML/IaC wave |
| Generic JSON | `bounded` | arbitrary JSON is intentionally quiet to avoid graph noise | accepted bounded behavior is documented and unchanged | docs build only unless scope changes | do not schedule unless requirement changes |

## Query-Surface And Documentation Matrix

| Workstream | Status | Gap now | Done means | Validation gate | Recommended split |
| --- | --- | --- | --- | --- | --- |
| API/MCP query surfacing | `partial` | some newly parsed semantics are not exposed through normal graph/story/context paths | each parity feature has a normal query path or an explicit non-goal | API tests, MCP proof, compose proof | pair with each feature wave |
| Language pages | `partial` | many pages still mark required features `partial` or `unsupported` | pages match implementation truth with no stale parity claims | docs build | update alongside each wave |
| Support maturity matrix | `partial` | matrix is coarser than the actual parity gap inventory | matrix and parity audit do not contradict each other | docs build | final sweep |
| Roadmap and architecture docs | `partial` | now mostly truthful, but must be kept in sync as rows close | current-state docs fully match branch truth | docs build | final sweep |

## Suggested Execution Waves

| Wave | Includes | Why this grouping works |
| --- | --- | --- |
| Wave 0 | operator/runtime contract rows | independent of parser work and unblocks cleaner operator truth |
| Wave 1 | SQL/dbt lineage | largest semantic gap and mostly isolated |
| Wave 2 | JavaScript, TypeScript, TSX, Python | shared graph/story/context promotion work for already-materialized parser semantics; canonical SCIP-backed `CALLS` edges plus same-file and import-driven cross-file generic `function_calls` are now Go-owned for JS/TS/TSX in the collector/reducer path, while Python still needs parser import-source identity before the same cross-file proof can close honestly. The remaining work is Python cross-file generic call parity, parser-first bare-name families, and the graph/story/context promotion work still missing for JS/TS/Python entities. Normal `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context metadata enrichment are now in place for graph-backed JS/TS/Python entities, `language-query` and `code/search` now also emit semantic summaries for matching graph-backed semantics, while type aliases, type annotations, and components are now also available through content-backed entity resolve/context surfaces, content-backed `code/search` name fallback, semantic-summary fallback for content-backed entities, and TSX component references can now surface through content-backed `code/relationships` fallback |
| Wave 3 | Terraform, Terragrunt, Kubernetes, ArgoCD, CloudFormation, Kustomize | shared IaC normalization and query-surface work |
| Wave 4 | Java, Kotlin, PHP, C, Rust, Elixir | long-tail graph promotions with lower coupling |
| Wave 5 | final query-surface proof, docs lock, full validation | closes the branch honestly |

## Approval Gate

Use this matrix to answer three questions before execution starts:

1. Which rows are required for merge on this branch?
2. Which rows can run in parallel without stepping on each other?
3. Which rows are truly bounded non-goals versus unfinished parity?

Do not treat a row as complete because the parser extracts it. A row is only
complete when persistence, query surfacing, tests, end-to-end proof, and docs
all agree.
