# Platform Context Graph OSS UI Base

Status: Draft v1 kickoff
Owner: `platform-context-graph`
Last updated: 2026-03-27

## Goal

Provide a strong single-user local/self-hosted visual foundation for query,
exploration, and graph-backed analysis using the existing OSS engine APIs.

The OSS UI base should make Platform Context Graph feel like a complete product
for an individual engineer or small self-hosted team without introducing any
enterprise-only concepts such as organizations, OIDC, RBAC, audit logs, or
service-account lifecycle management.

## Why Now

PCG already has the ingredients for a compelling UI surface:

- a stable HTTP API under `/api/v0`
- a visualization package and lightweight visualization server
- graph exploration patterns in the VS Code extension
- query flows for repositories, workloads, traces, impact, infra, and content

What is missing is a coherent single-user product surface that ties those
capabilities together into one discoverable UI.

## Success Criteria

- A user can search for entities, repositories, workloads, and resources from a
  single entry point.
- A user can open detail views for repositories, workloads, services, and
  resources without leaving the OSS UI.
- A user can run blast-radius, dependency-path, trace, and environment-compare
  flows from the UI using existing OSS APIs.
- A user can inspect ingestion health and status from the UI.
- The OSS UI remains free of enterprise concepts and uses the OSS API directly.
- The UI establishes core interaction patterns that the enterprise UI can later
  adapt without re-defining PCG query semantics.

## Primary User

Single-user self-hosted engineer, architect, or technical lead working directly
against a local or self-hosted PCG engine.

## Scope

### In Scope

- entity resolve and search
- repository, workload, service, and resource exploration
- blast radius and dependency-path views
- environment compare views
- ingestion health and status views
- graph visualization improvements over the current minimal viz surface
- local saved query presets or canned local query shortcuts

### Out of Scope

- OIDC
- organizations or workspaces
- RBAC
- audit logs
- service accounts
- token lifecycle UI
- enterprise onboarding flows
- secret management UX
- hosted AI workflows

## Product Constraints

- The UI must use the OSS API directly.
- No enterprise concepts may leak into OSS routes, payloads, or page structure.
- Existing `/api/v0/*` query semantics remain canonical.
- The UI can add client-side convenience state and saved local presets, but it
  must not redefine the underlying engine contract.

## User Workflows

### Workflow 1: Search And Explore

1. User lands on the OSS UI shell.
2. User searches for a symbol, repository, workload, or cloud resource.
3. UI resolves the query into one or more entities.
4. User opens a repository or workload detail page.
5. UI surfaces related context, code, infra, and trace information.

### Workflow 2: Pre-Change Analysis

1. User selects a service, workload, or resource.
2. UI runs blast radius, dependency path, or environment compare.
3. UI renders the result as a readable visual report with drill-down links.

### Workflow 3: Graph Inspection

1. User opens a graph or relationship exploration view.
2. UI shows a filtered graph visualization with semantic node types.
3. User clicks through to detail views or supporting content.

### Workflow 4: Runtime Health

1. User opens an ingestion/status screen.
2. UI shows health, ingester status, current/last runs, and coverage gaps.
3. User can move from status to affected repository or detail pages.

## Proposed UI Surface

- global search / resolve entry point
- left-nav or top-nav shell for core exploration flows
- repository detail pages
- workload/service detail pages
- resource detail pages
- impact and trace views
- compare-environments view
- ingestion health and status dashboard
- local saved query shortcut area

## Delivery Phases

### Phase 0: Architecture And Shell

- choose the OSS UI architecture inside this repo
- define route shell and app composition
- document API boundaries and non-goals

### Phase 1: Search And Explorer Foundation

- global search and entity resolve
- repository/workload/resource detail pages
- reusable result cards and summary panels

### Phase 2: Graph And Analysis Views

- graph and relationship visualization
- blast radius, dependency path, trace, and compare views

### Phase 3: Status And Local Presets

- ingestion health and status pages
- local saved query presets
- persisted local UI preferences where appropriate

### Phase 4: Polish And Verification

- docs and screenshots
- local Compose/dev verification
- UX polish and empty/error/loading states

## Acceptance Criteria

- Core explore flows work against the existing OSS `/api/v0/*` APIs.
- Graph/query semantics remain unchanged.
- The OSS UI feels satisfying as a single-user local workflow without any
  enterprise features.
- The UI creates reusable interaction patterns that the enterprise UI can learn
  from, but it remains product-distinct from the enterprise UI.

## Risks

- Allowing enterprise concepts to leak into the OSS UI would weaken the
  open/closed boundary.
- Over-investing in OSS admin surfaces would slow down enterprise delivery.
- Under-investing in the UX would weaken OSS adoption and product confidence.

## Dependencies

- existing OSS HTTP API
- current visualization package and server
- existing status and repository query surfaces
- optional lessons from the VS Code extension interaction model
