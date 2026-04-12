# PRD: PCG SQL + Data Intelligence

## Summary

Platform Context Graph should expand from repo-local SQL parsing into a
code-to-data-to-consumer intelligence system for DBAs, ETL owners, analytics
engineers, and platform teams. Users should be able to start from a table,
column, model, query, service, or dashboard and answer:

- who defines it
- who queries or transforms it
- what downstream assets depend on it
- how confident PCG is in the answer
- what coverage gaps remain

## Problem

PCG currently has a strong first SQL slice:

- repo-authored SQL objects
- table-level SQL relationships
- migration intelligence
- ORM and embedded SQL hooks
- SQL table blast radius
- content-entity impact resolution

That is useful for application teams, but it is not yet enough for daily
data-platform work. The missing gaps are the ones data and analytics teams care
about most:

- column-level lineage
- compiled and templated SQL understanding
- explicit parse confidence and unresolved lineage reporting
- warehouse object and query-history lineage
- dashboard and semantic-layer downstream mapping
- governance, quality, and contract overlays

## Users And Outcomes

### DBAs

Need:

- blast radius for schema and column changes
- dead or low-use object discovery
- protected field and policy-aware impact

Outcome:

PCG becomes a safer change-management tool for schema evolution.

### ETL and data engineers

Need:

- model-to-source and column-to-column lineage
- observed versus declared dependency views
- backfill and contract-change visibility

Outcome:

PCG becomes a cross-repo lineage and operational risk surface.

### Analytics engineers

Need:

- compiled SQL understanding for dbt-style workflows
- dashboard and semantic-layer downstream visibility
- partial lineage surfaced honestly, not silently dropped

Outcome:

PCG becomes a practical impact-analysis tool for analytics changes.

## Product Goals

- add a vendor-neutral data-intelligence graph model that supports future
  warehouse and BI adapters
- preserve repo-authored SQL and compiled artifacts as first-class citizens in
  the same graph as code and infra
- expose confidence, evidence source, and coverage gaps in query surfaces
- keep local release validation deterministic through replay fixtures and
  checked-in corpora

## Non-Goals

- making one warehouse vendor the hardcoded core model
- requiring live Snowflake, BigQuery, Power BI, Tableau, or Looker credentials
  for release gating
- replacing dedicated warehouse governance or BI observability products

## Core Model

Canonical entities:

- `DataAsset`
- `DataColumn`
- `AnalyticsModel`
- `QueryExecution`
- `DashboardAsset`
- `DataQualityCheck`

Canonical relationships:

- `COLUMN_DERIVES_FROM`
- `ASSET_DERIVES_FROM`
- `COMPILES_TO`
- `RUNS_QUERY_AGAINST`
- `POWERS`
- `ASSERTS_QUALITY_ON`
- `DECLARES_CONTRACT_FOR`
- `OWNS`
- `MASKS`

Identity rules:

- keep repo-authored SQL entities on `content_entity` IDs where that path is
  already the best fit
- use new canonical IDs for vendor-neutral data-native entities and future
  external assets

## Delivery Strategy

### Phase 1: Generic core and query surfacing

- canonical data-native entity types in the domain model
- query/entity resolution support
- generic entity context support
- impact-query compatibility
- plugin registry foundation

### Phase 2: Repo-local analytics lineage

- compiled and templated SQL normalization
- dbt-style compiled artifact support
- column-level lineage for the supported static subset
- confidence and unresolved-reference reporting

### Phase 3: Warehouse replay adapters

- generic warehouse adapter contract
- replay-backed object metadata and query-history ingestion
- declared versus observed dependency reconciliation

### Phase 4: BI and semantic downstreams

- dashboard and semantic-layer adapter contract
- replay-backed downstream asset mapping
- dashboard impact and lineage surfaces

### Phase 5: Governance and quality overlays

- tests and assertions on assets and columns
- contracts and change classification
- ownership and protected-field overlays

## Validation Strategy

Release-blocking validation should be local and deterministic.

Fixture groups:

- `sql_comprehensive`
- `analytics_compiled_comprehensive`
- `warehouse_replay_comprehensive`
- `bi_replay_comprehensive`

Rules:

- reset graph/content state between profile groups
- no release gate depends on live vendor credentials
- future live smoke checks remain optional and non-blocking until explicitly
  promoted

## Current Branch Deliverables

This branch starts the roadmap with the generic foundation slice:

- canonical data-intelligence entity types
- data-native resolution and context support
- generic impact-query compatibility
- plugin registration foundation
- repo-tracked roadmap and local validation guidance
