# GitOps, Story, And Documentation Orchestration Implementation Plan

## Goal

Deliver one additive PR that lets existing story surfaces generate stronger GitOps, documentation, and support answers by combining graph/context evidence with targeted Postgres content evidence.

## Scope

The implementation covers:

- `get_repo_story`
- `get_workload_story`
- `get_service_story`
- `trace_deployment_chain`

It adds:

- `gitops_overview`
- `documentation_overview`
- `support_overview`
- matching `story_sections`

It also adds the first content-orchestration layer for documentation answers.

## Architectural approach

### 1. Keep builders as orchestrators

The repository and workload story builders should stay thin. They assemble sections and delegate shaping to helper modules.

### 2. Split responsibilities into small helpers

Use focused Python modules:

- `story_gitops.py`
- `story_documentation.py`
- `story_support.py`

This keeps files under the repo’s 500-line guardrail and avoids turning one story builder into a giant mixed-responsibility module.

### 3. Fetch content evidence before final shaping

Content evidence is attached before story assembly:

- repository stories collect repo and related-config evidence
- workload and service stories collect workload repo evidence plus related GitOps repos
- deployment-chain traces collect the same evidence for a repo-shaped deployment answer

### 4. Prefer targeted evidence

The content collector should prefer:

- README files
- runbook and on-call Markdown
- docs Markdown
- GitOps config evidence through indexed content search

V1 avoids full-document ingestion into story responses.

## Delivered helper responsibilities

### `story_gitops.py`

- shape GitOps ownership
- shape environments
- shape chart and values layers
- shape rendered and supporting resources
- provide a concise section summary

### `story_documentation.py`

- collect Postgres-backed file and search evidence
- build graph-first evidence markers
- shape the documentation overview
- provide a concise section summary

### `story_support.py`

- build a support-oriented overview
- derive first investigation paths from available evidence
- provide a concise section summary

## Query-layer integration

### Repository stories

- enrich repo context with `documentation_evidence`
- build additive story sections and overviews

### Workload and service stories

- merge richer repo-backed GitOps fields into workload context
- enrich workload context with `documentation_evidence`
- build additive story sections and overviews

### Deployment traces

- reuse the same GitOps and documentation helpers
- surface the same additive overview fields in trace responses

## Testing strategy

### Red-green-refactor slices

1. failing unit tests for new story fields
2. failing unit test for Postgres-backed content evidence collection
3. implementation to satisfy those tests
4. handler-level trace test for additive deployment-chain coverage
5. broader API and MCP contract tests

### Required verification

- unit tests for story shaping
- unit tests for deployment trace enrichment
- integration API story contract tests
- integration MCP story contract tests
- OpenAPI contract tests
- docs smoke and MkDocs strict build

## Documentation updates

Public docs must explain the orchestration principle directly:

- story tools plan the answer
- content tools fetch exact evidence
- documentation generation uses both

Required touchpoints:

- `docs/docs/guides/mcp-guide.md`
- `docs/docs/reference/mcp-reference.md`
- `docs/docs/reference/http-api.md`
- `docs/docs/guides/starter-prompts.md`
- `docs/docs/use-cases.md`

Internal docs updated:

- this implementation plan
- the paired design doc
- docs inventory

## Risks and mitigations

### Risk: story payload bloat

Mitigation:

- keep new fields additive and compact
- prefer short summaries plus artifact references
- avoid embedding raw content

### Risk: misleading support guidance

Mitigation:

- only emit investigation paths when backed by graph or content evidence
- carry explicit limitations when evidence is thin

### Risk: GitOps story overfitting one estate

Mitigation:

- keep the data model generic
- shape around controllers, values layers, and rendered resources instead of one repo naming scheme

## Follow-on work after v1

- stronger ArgoCD owner inference from ApplicationSet and multi-source inputs
- first-class documentation export surfaces
- persona-specific templates for onboarding, architecture, and support docs
- richer entity-content integration when source snippets materially improve the answer
