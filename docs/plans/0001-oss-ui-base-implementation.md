# OSS UI Base Implementation Plan

Goal: deliver a minimal but coherent single-user OSS UI that proves the core
query and exploration experience directly against the existing PCG API.

## Phase 0: Architecture And Shell

- Decide whether the OSS UI lives inside the existing visualization package or a
  dedicated frontend subtree within this repo.
- Define the route shell, global navigation, and core page inventory.
- Document the strict boundary: direct OSS API use only, no enterprise concepts.
- Add developer docs for local OSS UI startup and API expectations.

## Phase 1: Search And Explorer Foundation

- Implement a global search surface backed by `entities/resolve` and code/content
  search routes.
- Add detail pages for repositories, workloads/services, and infra resources.
- Add reusable summary cards for context, dependencies, and supporting content.
- Verify detail views against fixture data and local self-hosted API runs.

## Phase 2: Graph And Analysis Views

- Improve graph visualization beyond the current minimal viz surface.
- Add blast radius, dependency path, trace, and environment compare screens.
- Reuse existing query results instead of inventing a second graph semantics
  layer in the UI.
- Verify drill-down paths from graph nodes into detail pages.

## Phase 3: Runtime Health And Local Presets

- Add ingestion health, ingester status, and coverage views.
- Add local saved query presets and shortcuts.
- Keep preset persistence local-first unless a future OSS-safe persistence layer
  is explicitly designed.

## Phase 4: Polish And Verification

- Improve empty, loading, and error states.
- Add documentation and screenshots to the OSS docs site or internal docs as
  appropriate.
- Verify the OSS UI against local Compose or equivalent self-hosted flow.
- Confirm the final surface still contains no enterprise-only concepts.

## Deliverables

- OSS UI route shell
- search and explorer flows
- graph and analysis views
- status and health pages
- local saved query presets
- docs describing the OSS UI contract and limits

## Verification Checklist

- search works against real `/api/v0/*` routes
- repository and workload detail pages load real contexts
- impact and trace views render from existing query contracts
- status views read current ingester endpoints
- no enterprise-only routes, headers, or concepts are required
