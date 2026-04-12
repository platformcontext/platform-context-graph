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
- explicit unresolved-reference reporting for wildcard projections
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
  tests/unit/parsers/test_sql_parser.py \
  tests/unit/parsers/test_python_sql_mappings.py \
  tests/unit/parsers/test_go_sql_extraction.py \
  tests/unit/relationships/test_sql_links.py \
  tests/unit/query/test_change_surface.py \
  tests/unit/mcp/test_ecosystem_sql_blast_radius.py -q
```

### Compiled analytics gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_plugins.py \
  tests/unit/data_intelligence/test_dbt_compiled_sql.py \
  tests/unit/parsers/test_json_parser.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/tools/test_graph_builder_schema.py -q
```

### Warehouse replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_plugins.py \
  tests/unit/data_intelligence/test_warehouse_replay.py \
  tests/unit/parsers/test_json_parser.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py -q
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
  tests/unit/parsers/test_json_parser.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py -q
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
  tests/unit/parsers/test_json_parser.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py \
  tests/unit/query/test_change_surface.py -q
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

### Quality replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_quality_replay.py \
  tests/unit/parsers/test_json_parser.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/tools/test_graph_builder_schema.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py \
  tests/unit/query/test_change_surface.py -q
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
