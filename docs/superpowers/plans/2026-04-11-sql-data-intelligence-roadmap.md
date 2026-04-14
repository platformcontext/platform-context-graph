# Roadmap: SQL + Data Intelligence

## Branch Goal

Deliver the vendor-neutral foundation for PCG’s SQL and data-intelligence
story on one long-lived feature branch, then layer in replay-backed adapters
and richer lineage slices milestone by milestone.

## Milestone Order

### Milestone 1: Generic Data Core

Status on this branch:

- canonical entity types for data-native graph nodes
- entity resolution support
- entity context support
- impact-query compatibility
- plugin registry foundation
- local validation guidance

Acceptance:

- `data_asset`, `data_column`, `analytics_model`, `query_execution`,
  `dashboard_asset`, and `data_quality_check` are valid canonical types
- resolution, context, and impact queries accept those IDs without special-case
  callers

### Milestone 2: Repo-Local Analytics Layer

Deliver:

- compiled SQL normalization pipeline
- dbt-style compiled model support
- static column-lineage extraction for supported SQL shapes
- parse confidence and unresolved-reference surfaces

Acceptance:

- exact source-to-model and column-to-column assertions from checked-in replay
  and compiled fixtures
- partial lineage is surfaced explicitly

Status on this branch:

- checked-in `analytics_compiled_comprehensive` replay fixture
- dbt-style compiled manifest normalization
- supported-subset column lineage from compiled SQL projections
- explicit unresolved-reference reporting for remaining unsupported derived
  expressions
- manifest-known wildcard projections now expand into exact column lineage,
  removing the previous `orders_expanded` partial-gap case from the checked-in
  replay fixture
- simple CTE-backed compiled models now propagate renamed final projections
  back to base source columns in the checked-in dbt replay fixture
- unqualified columns now resolve through one visible source or CTE binding,
  and ambiguous bare references surface an explicit lineage gap instead of a
  silent empty result
- simple scalar wrappers such as `upper(column)` and
  `coalesce(column, 'literal')` now stay on the supported lineage path, which
  reduces partial-coverage noise to the remaining aggregate and multi-input
  expression cases
- typed scalar transforms such as `cast(column as type)` and
  `date_trunc('day', column)` now stay on the supported lineage path as well,
  which broadens safe analytics-model coverage without treating aggregates as
  fully understood
- supported non-identity compiled-lineage edges now persist transform metadata
  (`transform_kind` and `transform_expression`) for row-preserving wrappers
  such as `upper`, `coalesce`, `cast`, and `date_trunc`
- transform metadata now propagates through simple CTE reuse, so direct final
  projections from transformed intermediate columns keep the original compiled
  SQL context instead of collapsing back to a plain rename
- one-column `CASE` expressions and simple arithmetic expressions with literal
  operands now stay on the supported lineage path as transform-aware derived
  columns, which reduces avoidable partial coverage for common analytics
  bucketing and scaling patterns
- row-level multi-source transforms now stay on the supported lineage path as
  well, including `concat(...)`, multi-source `CASE`, and arithmetic
  expressions across multiple source columns, which closes a larger remaining
  subset of compiled-model partial noise without overstating aggregate or
  templated semantics
- aggregate and window-style compiled expressions now preserve exact referenced
  source columns plus transform metadata on `COLUMN_DERIVES_FROM` edges, while
  still surfacing explicit partial-gap reasons for aggregate and window
  semantics that PCG does not yet model completely
- unresolved Jinja-style templating delimiters and package-qualified macro
  calls now short-circuit to explicit partial-gap reasons instead of producing
  misleading source-alias misses or weak generic derived-expression noise
- remaining unsupported derived cases now surface more specific partial-gap
  reasons, separating aggregate expressions from multi-input transforms so repo
  stories and model samples are more actionable
- analytics-model entity context now exposes compiled-lineage coverage state,
  confidence, materialization, projection count, and unresolved reasons and
  expressions
- data-column entity context now exposes supported compiled-lineage transform
  summaries, so downstream consumers can see when a column derives through a
  preserved transform instead of a direct passthrough
- repository context and story summaries now explain partial compiled lineage
  with aggregated unresolved-gap reasons instead of count-only wording
- repository analytics-model samples now prioritize partial models first and
  surface compiled artifact paths plus unresolved-gap detail on the returned
  items
- `manifest.json` parsing through the JSON config lane
- graph/content registration for `AnalyticsModel`, `DataAsset`, and `DataColumn`
- post-commit materialization for `COMPILES_TO`, `ASSET_DERIVES_FROM`, and
  `COLUMN_DERIVES_FROM`

### Milestone 3: Warehouse Adapter Framework

Deliver:

- vendor-neutral warehouse adapter contract
- replay-backed fixture loaders for object metadata and query history
- normalized evidence output into the core graph

Acceptance:

- adapters can register without reshaping the core entity model
- replay fixtures can materialize `DataAsset`, `DataColumn`, and
  `QueryExecution` entities locally

Status on this branch:

- checked-in `warehouse_replay_comprehensive` replay fixture
- `WarehouseReplayPlugin` as the first warehouse-category replay adapter
- `warehouse_replay.json` parsing through the JSON config lane
- graph/content registration for `QueryExecution`
- post-commit materialization for observed `RUNS_QUERY_AGAINST` edges
- repository context and story summaries include warehouse query replay counts

### Milestone 4: First Warehouse Adapter

Deliver:

- first end-to-end warehouse replay implementation
- declared versus observed lineage reconciliation
- hot and low-use asset signals from replay history

Acceptance:

- PCG can explain both static and observed lineage for one warehouse replay
  corpus

Status on this branch:

- combined `analytics_observed_reconciliation` fixture with one shared, one
  declared-only, and one observed-only asset dependency
- repo context reconciliation summary for declared `ASSET_DERIVES_FROM` versus
  observed `RUNS_QUERY_AGAINST` asset names
- repo context and story summaries now classify replay-observed hot assets
  (touched by multiple warehouse queries) and low-use assets (seen only once),
  which turns replay history into a more operational signal for DBAs and ETL
  owners instead of leaving it as raw query counts alone
- `data_asset` entity context now surfaces observed usage level and query-count
  signals directly from replay history, so warehouse-heavy assets can be
  recognized as hot or low-use without leaving the persona-focused entity view
- repository story wording for aligned and mismatched declared-versus-observed
  lineage
- generic impact responses and content-entity context now expose
  `lineage_evidence` summaries that distinguish declared, observed, and
  combined lineage signals
- graph-backed integration coverage for reconciliation mismatch cases

### Milestone 5: BI and Semantic Adapters

Deliver:

- dashboard and semantic-layer plugin contract
- replay-backed downstream dataset and column mapping

Acceptance:

- PCG can answer which dashboards break when a data asset or column changes

Status on this branch:

- checked-in `bi_replay_comprehensive` replay fixture with one dashboard and
  both asset-level and column-level downstream mappings
- `BIReplayPlugin` as the first BI-category replay adapter
- `bi_replay.json` parsing through the JSON config lane
- graph/content registration for `DashboardAsset`
- post-commit materialization for `POWERS` edges from `DataAsset` and
  `DataColumn` to `DashboardAsset`
- repository context and story summaries include dashboard counts and downstream
  `POWERS` coverage
- graph-backed integration coverage for persisted dashboard nodes and consumer
  relationships
- checked-in `semantic_replay_comprehensive` replay fixture with one semantic
  model asset, exact field lineage, and a downstream dashboard consumer
- `SemanticReplayPlugin` as the first semantic-category replay adapter
- `semantic_replay.json` parsing through the JSON config lane
- semantic-layer datasets reuse `DataAsset` and semantic fields reuse
  `DataColumn`, avoiding a wider canonical model change
- post-commit materialization for semantic `ASSET_DERIVES_FROM` and
  `COLUMN_DERIVES_FROM` edges through the existing data-intelligence
  relationship finalizer
- graph-backed integration coverage for warehouse-column-to-semantic-field
  change surface and downstream dashboard impact

### Milestone 6: Governance and Quality

Deliver:

- ownership overlays
- tests and assertions linked to data assets
- contract and protected-field impact classification

Acceptance:

- impact responses distinguish additive, breaking, quality-risk, and
  governance-sensitive changes

Status on this branch:

- checked-in `quality_replay_comprehensive` replay fixture with asset-level and
  column-level checks
- `QualityReplayPlugin` as the first quality-category replay adapter
- `quality_replay.json` parsing through the JSON config lane
- graph/content registration for `DataQualityCheck`
- post-commit materialization for `ASSERTS_QUALITY_ON` edges from
  `DataQualityCheck` to `DataAsset` and `DataColumn`
- repository context and story summaries include quality-check counts and
  sample checks
- graph-backed integration coverage for persisted quality checks and
  change-surface traversal from changed columns to downstream checks
- checked-in `governance_replay_comprehensive` replay fixture with one owner,
  one contract, and one protected column overlay
- `GovernanceReplayPlugin` as the first governance-category replay adapter
- `governance_replay.json` parsing through the JSON config lane
- graph/content registration for `DataOwner` and `DataContract`
- post-commit materialization for `OWNS`, `DECLARES_CONTRACT_FOR`, and
  protected-column `MASKS` edges
- governance metadata overlays applied onto `DataAsset` and `DataColumn`
  targets, including owner teams, contract levels, change policies, and
  protected-field metadata
- repository context and story summaries include owner counts, contract counts,
  protected-column coverage, and explicit `masks` relationship counts
- graph-backed integration coverage for persisted governance nodes, exact
  overlay relationships, exact `MASKS` edges, and protected-column metadata on
  target columns
- path-aware change classification treats `MASKS` the same as other
  governance-overlay relationships, so protected sibling columns do not
  over-propagate governance-sensitive blast radius through shared contracts
- `get_entity_context` for `data_asset`, `data_column`, `analytics_model`,
  `query_execution`, `dashboard_asset`, and `data_quality_check` now returns a
  persona-friendly summary with lineage evidence, change classification,
  ownership, contracts, governance metadata, downstream impact counts, and
  sample impacted entities

## MCP Persona Workflows

These workflows are the practical reason this branch exists. The parser and
graph work matter only if they improve the answers MCP can give to data-heavy
questions through `resolve_entity`, `get_entity_context`,
`get_repository_context`, `get_repository_story`, and `find_change_surface`.

### DBA workflows

- What breaks if this table or column changes?
  Start from a `data_asset` or `data_column` and use `find_change_surface` to
  see downstream semantic fields, dashboards, and data-quality checks.
- Which warehouse assets are actually hot versus only declared in code?
  Use `get_entity_context` or `get_repository_context` to inspect replay-backed
  observed-usage signals such as hot assets and low-use assets.
- Who owns this protected column and how is it governed?
  Use `get_entity_context` on a `data_column` to surface owner names, teams,
  contracts, sensitivity, protection state, and `MASKS`-backed governance
  context.

### ETL and data-engineering workflows

- Does declared lineage match observed warehouse usage?
  Use `get_repository_context` and `get_repository_story` to compare declared
  `ASSET_DERIVES_FROM` dependencies against observed `RUNS_QUERY_AGAINST`
  history.
- Which downstream quality checks are tied to this dataset or column?
  Use `find_change_surface` to follow `ASSERTS_QUALITY_ON` edges into failing
  or high-severity checks before changing upstream transforms.
- Why is this model still partial?
  Use `get_entity_context` on an `analytics_model` to inspect parse state,
  confidence, unresolved reasons, and sample unresolved expressions.

### Analytics-engineering workflows

- What compiled SQL produced this model or field?
  Use `get_entity_context` on an `analytics_model` to inspect materialization,
  compiled artifact path, and unresolved-gap detail from the checked-in replay
  corpora.
- How was this derived column transformed?
  Use `get_entity_context` on a `data_column` to surface preserved
  `transform_kind` and `transform_expression` summaries for supported compiled
  lineage.
- Which dashboards or semantic fields depend on this warehouse column?
  Use `find_change_surface` or repository story/context surfaces to walk from
  warehouse columns into semantic fields and dashboard consumers.

### Platform-team workflows

- Can MCP resolve data-native things directly, not only repos and workloads?
  `resolve_entity` now accepts data-native IDs and ranked matches for
  `data_asset`, `data_column`, `analytics_model`, `query_execution`,
  `dashboard_asset`, and `data_quality_check`.
- Can one repo story summarize the data posture of a service or analytics repo?
  `get_repository_context` and `get_repository_story` now summarize compiled
  lineage coverage, warehouse replay usage, BI/semantic consumers, governance,
  and quality overlays in one response.
- Can impact answers classify risk instead of only counting dependents?
  `find_change_surface` now distinguishes additive, breaking, quality-risk,
  governance-sensitive, and informational outcomes for data-native entities.

## Remaining Work and Effort

Assumption for sizing below: one focused engineer already familiar with the
current PCG query and graph architecture. Estimates exclude release and deploy
overhead.

| Work item | Why it matters | Rough effort |
| --- | --- | --- |
| Templated SQL and macro resolution | Biggest remaining trust gap for dbt-style analytics repos; reduces partial lineage from unresolved Jinja and package macros. | Large, about 2-3 weeks |
| Deeper compiled SQL semantics | Improves column-lineage fidelity for harder cases such as unions, nested subqueries, richer window logic, and aggregate semantics. | Large, about 2-4 weeks |
| Real-repo data-intelligence validation corpus | Moves this branch from strong fixture confidence to stronger pre-image regression coverage on realistic local repos. | Medium, about 1-1.5 weeks |
| Warehouse adapter realism beyond replay | Needed before claiming production-grade DBA utility; likely starts with richer replay evidence and may end with one live adapter behind guarded config. | Extra large, about 3-5 weeks |
| BI and semantic adapter breadth | Extends the current first-slice dashboard and semantic coverage into broader downstream consumer systems and richer field mappings. | Large, about 2-3 weeks |
| Governance and contract depth | Adds richer policy, masking, ownership, and contract semantics beyond the first protected-column overlay and `MASKS` edge. | Medium, about 1-2 weeks |
| MCP persona polish | Turns the existing graph and query surface into easier day-to-day workflows through better prompts, examples, and response shaping. | Medium, about 1 week |

### Recommended next sequence

1. Templated SQL and macro resolution.
2. Deeper compiled SQL semantics.
3. Real-repo data-intelligence validation corpus.
4. Warehouse adapter realism beyond replay.
5. BI and semantic adapter breadth.
6. Governance and contract depth.
7. MCP persona polish.

## Runtime Ownership

This branch spans all three long-running PCG runtimes, but not equally. The
important architectural rule is:

- the ingester owns parse-time extraction and indexing-time materialization
- the API owns read/query/MCP packaging
- the resolution engine owns fact projection, but it does not yet own the
  SQL/data-intelligence relationship builders added on this branch

### Ingester responsibilities on this branch

- SQL and data-intelligence extraction runs during repository parsing through
  `parsers/`, including:
  - `.sql` parser output
  - ORM table-mapping extraction
  - embedded SQL extraction
  - replay-backed JSON normalization for compiled analytics, warehouse, BI,
    semantic, quality, and governance fixtures
- In direct graph-build mode, the ingester runs post-parse materialization
  inline through `GraphBuilder._create_all_sql_relationships`, which delegates
  to both SQL link creation and data-intelligence link creation.
- In the facts-first coordinator path, the ingester still triggers the final
  SQL/data-intelligence materialization stage after inline projection through
  `indexing/coordinator_facts_finalize.py`.
- Practical meaning: the branch's parser and relationship logic currently lives
  in the indexing/finalization boundary, not in the request-serving path.

### API and MCP responsibilities on this branch

- The API does not parse repositories or create lineage edges.
- The API reads already-materialized graph and content state and exposes it
  through:
  - `resolve_entity`
  - `get_entity_context`
  - `get_repository_context`
  - `get_repository_story`
  - `find_change_surface`
- MCP uses the same query layer as the HTTP API, so this branch helps MCP only
  after the ingester has indexed and materialized the new graph state.
- Practical meaning: if answers are missing in MCP, the first suspicion should
  usually be indexing/materialization coverage, not API runtime behavior.

### Resolution-engine responsibilities on this branch

- The resolution engine still owns fact work-item projection into canonical
  graph state.
- It is adjacent to this roadmap because the ingester can project the same
  facts-first path inline during indexing cutover.
- However, the branch's new SQL/data-intelligence relationship builders are
  not currently hosted inside `resolution/`.
- Practical meaning: the resolution engine matters for the facts-first
  projection foundation, but it is not yet the runtime that creates the new
  SQL/data-intelligence relationship families after projection.

### Architecture concern to keep in view

The current placement is good enough for feature delivery, but it is also the
main architectural risk left on this branch:

- parser extraction belongs on the ingester
- query shaping belongs on the API
- relationship materialization is currently split between resolution-owned
  projection foundations and ingester-owned post-commit finalization

That split is acceptable for the milestone, but we should treat it as a
follow-up design pressure point if we want a cleaner long-term story.

## Chunked Delivery Plan

The remaining work should be executed as full, reviewable chunks on this
branch, not as isolated micro-slices. Each chunk ends only after code, tests,
and local validation are green.

### Chunk 1: Templated SQL and macro resolution

Primary runtime surface:
- Ingester

Why this chunk exists:
- This is the biggest trust gap for analytics engineers using dbt-style or
  templated SQL because unresolved macros currently force partial lineage.

Done means:
- unresolved Jinja and package-qualified macro cases are classified more
  precisely
- supported macro-expansion or templated-resolution paths produce better
  lineage instead of generic partial gaps
- analytics-model context explains exactly what was resolved and what remains
  unresolved

Blocking validation:
- compiled analytics unit suites
- `tests/integration/test_mcp_data_intelligence_queries.py`
- checked-in compiled analytics replay fixture coverage

Estimated effort:
- Large, about 2-3 weeks

### Chunk 2: Deeper compiled SQL semantics

Primary runtime surfaces:
- Ingester
- API

Why this chunk exists:
- The current lineage is strong for supported projections, but deeper SQL
  semantics are required before DBAs and analytics engineers can trust complex
  model answers.

Done means:
- richer support for unions, nested subqueries, more window cases, and broader
  aggregate-awareness
- exact column-lineage assertions expand beyond the current supported subset
- API/MCP summaries expose the richer transform evidence clearly

Blocking validation:
- compiled analytics unit suites
- exact graph integration assertions for column lineage
- targeted entity-context and change-surface tests

Estimated effort:
- Large, about 2-4 weeks

### Chunk 3: Real-repo validation corpus and local gate

Primary runtime surface:
- Ingester

Why this chunk exists:
- We need stronger confidence that parser extraction and relationship building
  hold up on real repos before the next image or broader release claims.

Done means:
- the checked-in fixtures stay the exact regression source of truth
- local real-repo validation profiles run cleanly against the required repos
- scratch-cloned external repos cover ORM and Go relationship lanes
- failures identify missing entities or missing edge families directly

Blocking validation:
- new SQL/data validator profiles
- local Neo4j/Postgres graph-backed validation runs
- existing SQL unit and integration suites

Estimated effort:
- Medium, about 1-1.5 weeks

### Chunk 4: Warehouse adapter realism beyond replay

Primary runtime surfaces:
- Ingester
- API

Why this chunk exists:
- Replay fixtures prove the model, but DBAs need stronger answers around
  observed usage, hot assets, and declared-versus-observed mismatches.

Done means:
- warehouse replay normalization grows to cover more realistic metadata and
  query-history shapes
- observed lineage and usage signals are queryable and easy to explain
- entity and repository context present confidence and evidence-source
  breakdowns cleanly

Blocking validation:
- warehouse replay unit and graph integration suites
- repository context/story tests
- change-surface regression coverage for observed dependencies

Estimated effort:
- Extra large, about 3-5 weeks

### Chunk 5: BI and semantic downstream breadth

Primary runtime surfaces:
- Ingester
- API

Why this chunk exists:
- The story is incomplete if we cannot reliably show which dashboards and
  semantic fields break when an upstream asset or column changes.

Done means:
- broader downstream consumer coverage beyond the first replay fixtures
- stronger column-level mappings from warehouse and semantic layers into BI
  consumers
- MCP examples can walk from source asset to semantic field to dashboard

Blocking validation:
- BI and semantic unit suites
- graph-backed downstream-impact assertions
- entity-context and change-surface regression tests

Estimated effort:
- Large, about 2-3 weeks

### Chunk 6: Governance, contracts, and persona polish

Primary runtime surfaces:
- Ingester
- API

Why this chunk exists:
- This is the layer that turns good lineage into operationally useful answers
  for DBAs, ETL owners, and platform teams.

Done means:
- richer policy and contract overlays beyond the first protected-column slice
- persona-facing MCP answers explain ownership, protection, risk class, and
  downstream impact clearly
- examples and docs show how this work is meant to be used day to day

Blocking validation:
- governance and change-classification suites
- entity-context and repository-story suites
- strict docs build

Estimated effort:
- Medium, about 1-2 weeks for governance depth, plus about 1 week for MCP
  persona polish

## Sequence And Stop Points

To keep this branch healthy, each chunk should stop at these review points:

1. Design confirmation for the chunk boundary and runtime placement.
2. TDD-first implementation with the smallest useful vertical slice.
3. Local graph-backed verification, not only unit tests.
4. Roadmap and PR update summarizing what changed, what runtime owns it, and
   what remains.

We should not blend multiple chunks into one “big push.” The right rhythm is:
finish a whole chunk, verify it locally, report the result, then begin the next
chunk.

## Local Validation

### Foundation gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/query/test_entity_resolution.py \
  tests/unit/query/test_entity_context.py \
  tests/unit/query/test_change_surface.py \
  tests/unit/data_intelligence/test_plugins.py -q
```

### SQL regression gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/relationships/test_sql_links.py \
  tests/unit/query/test_change_surface.py \
  tests/unit/mcp/test_ecosystem_sql_blast_radius.py -q

cd go
go test ./internal/parser -run 'TestDefaultEngineParsePathSQL|TestDefaultEngineParsePathGoEmbeddedSQLQueries' -count=1
```

### Compiled analytics gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_plugins.py \
  tests/unit/data_intelligence/test_dbt_sql_lineage.py \
  tests/unit/data_intelligence/test_dbt_compiled_sql.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/query/test_entity_context.py \
  tests/unit/tools/test_graph_builder_schema.py -q

cd go
go test ./internal/parser -run 'TestDefaultEngineParsePathJSON(DBTManifest|PreservesDocumentOrderForMetadataAndConfigBuckets|CloudFormation)' -count=1
```

### Warehouse replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_plugins.py \
  tests/unit/data_intelligence/test_warehouse_replay.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py -q

cd go
go test ./internal/parser -run 'TestDefaultEngineParsePathJSONWarehouseReplay' -count=1
```

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PYTHONPATH=src

uv run pytest \
  tests/integration/test_warehouse_replay_graph.py \
  tests/integration/test_mcp_data_intelligence_queries.py -q
```

### BI replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_bi_replay.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py -q

cd go
go test ./internal/parser -run 'TestDefaultEngineParsePathJSONBIReplay' -count=1
```

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PYTHONPATH=src

uv run pytest \
  tests/integration/test_warehouse_replay_graph.py \
  tests/integration/test_mcp_data_intelligence_queries.py -q
```

### Semantic replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_semantic_replay.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py \
  tests/unit/query/test_change_surface.py -q

cd go
go test ./internal/parser -run 'TestDefaultEngineParsePathJSONSemanticReplay' -count=1
```

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PYTHONPATH=src

uv run pytest \
  tests/integration/test_warehouse_replay_graph.py \
  tests/integration/test_mcp_data_intelligence_queries.py -q
```

### Governance replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_governance_replay.py \
  tests/unit/content/test_data_intelligence_ingest.py \
  tests/unit/relationships/test_data_intelligence_governance_links.py \
  tests/unit/query/test_change_surface_classification.py \
  tests/unit/query/test_repository_context_data_governance.py \
  tests/unit/query/test_story_data_governance.py \
  tests/unit/tools/test_graph_builder_schema.py -q

cd go
go test ./internal/parser -run 'TestDefaultEngineParsePathJSONGovernanceReplay' -count=1
```

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PYTHONPATH=src

uv run pytest \
  tests/integration/test_governance_replay_graph.py \
  tests/integration/test_mcp_data_governance_queries.py \
  tests/integration/test_mcp_data_change_classification.py -q
```

### Quality replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_quality_replay.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/tools/test_graph_builder_schema.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py \
  tests/unit/query/test_change_surface.py -q

cd go
go test ./internal/parser -run 'TestDefaultEngineParsePathJSONQualityReplay' -count=1
```

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PYTHONPATH=src

uv run pytest \
  tests/integration/test_warehouse_replay_graph.py \
  tests/integration/test_mcp_data_intelligence_queries.py -q
```

### Reconciliation gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py \
  tests/unit/query/test_change_surface.py \
  tests/unit/query/test_entity_context.py \
  tests/unit/query/test_entity_resolution.py -q
```

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PYTHONPATH=src

uv run pytest \
  tests/integration/test_sql_graph.py \
  tests/integration/test_warehouse_replay_graph.py \
  tests/integration/test_mcp_data_intelligence_queries.py -q
```

### Docs and quality gate

```bash
python3 scripts/check_python_file_lengths.py --max-lines 500
git diff --check
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

## Branch Defaults

- keep the core model vendor-neutral
- add adapters through plugin registration, not core rewrites
- prefer replay fixtures over live-system gating
- keep repo-authored SQL and compiled artifacts first-class alongside future
  warehouse and BI nodes
