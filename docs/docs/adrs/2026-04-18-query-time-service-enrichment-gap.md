# ADR: Relationship-Mapping Accuracy And MCP Contract Parity — Closing the Gap Between Go and Python Data Planes

**Date:** 2026-04-18
**Status:** Proposed
**Authors:** Allen Sanabria
**Deciders:** Platform Engineering

---

## Context

The Go data plane has reached structural correctness — 896 repos indexed with zero
terminal failures after the cross-phase EntityNotFound race fix. However, validation
of the MCP tool surface against the QA Python instance reveals that the Go query
layer does not yet provide **relationship-mapping accuracy** or **contract
correctness** at the level required for the same service investigation workflow.

The newest validation also shows a second problem: the test-machine E2E MCP is now
reachable and populated, but it does not yet provide **tool-contract parity**,
**service-query parity**, or **relationship-parity** with the QA MCP surface. In
practice, QA can answer service-oriented questions for `sample-service-api`, while E2E
currently answers some repository-oriented and deployment-artifact questions
reliably but still misses or misclassifies important service relationships.

This ADR documents the gap with concrete evidence, proposes architectural options for
closing it, and recommends a phased approach. It also serves as the
**contract-parity ADR** for the overlapping QA and E2E MCP capabilities used in the
service investigation workflow.

The governing principle for this ADR is:

- **Accuracy first**: if identity resolution, relationship mapping, or deployment
  provenance are wrong, the rest of the MCP surface is not trustworthy.
- **Compatibility second**: overlapping QA and E2E tools should accept comparable
  inputs and return semantically comparable outputs unless they are intentionally
  different.
- **Enrichment third**: richer stories, framework summaries, and operator
  narratives matter, but only after the underlying mappings are correct.

---

## Evidence: sample-service-api Comparison (2026-04-18)

### MCP Availability And Contract Parity

Both MCP servers are now reachable from Codex.

| Probe | Go E2E MCP (`mcp__pcg_e2e__`) | QA MCP (`mcp__pcg__`) |
|---|---|---|
| `list_indexed_repositories()` | Works | Works |
| `get_ecosystem_overview()` | Works | Works |
| `resolve_entity("sample-service-api")` | Fails with `HTTP 400: {"detail":"name is required"}` | Works |
| `get_service_story("workload:sample-service-api")` | Fails with `HTTP 404: service not found` | Works |
| `search_file_content(pattern="sample-service-api...")` | Fails with `HTTP 400: repo_id is required` | Cross-repo capable through current wrapper |

This matters because part of the observed gap is no longer just "missing facts."
The E2E MCP surface itself is currently using a different request contract than the
QA MCP wrapper expects.

### MCP Capability Matrix (QA vs E2E)

The table below focuses on overlapping capabilities that should behave similarly
across the QA and E2E MCP surfaces.

| Capability Family | Representative Tools | Go E2E MCP | QA MCP | Better Today | Finding |
|---|---|---|---|---|---|
| Inventory / ecosystem | `list_indexed_repositories`, `get_ecosystem_overview` | Works; repo inventory shape is richer | Works; ecosystem narrative is richer | Mixed | E2E is stronger for raw repo metadata; QA is stronger for operator-facing summarization |
| Name -> canonical ID resolution | `resolve_entity("sample-service-api")` | Fails with `HTTP 400: {"detail":"name is required"}` | Works; returns ranked matches with confidence scoring, finds both repos and workloads | QA | Contract mismatch; E2E dispatch passes `query` in body but API expects `name` field |
| Service story / service context | `get_service_story`, `get_service_context` | `404 service not found` for qualified ID; plain-name path returns flat text ("No deployed instances found") | Works with qualified ID and returns rich structured service view with story_sections, deployment_overview, documentation_overview, support_overview | QA | E2E wrapper/path is not qualified-ID compatible and loses service semantics |
| Workload context | `get_workload_context("workload:sample-service-api")` | Works, but returns flat object with dependencies, 3 script `main` entry_points, 1 K8sResource, `instances: []` | Works, returns full API surface (21 endpoints with methods/operation_ids), hostnames (2), observed_config_environments, coverage data, and limitations | QA | E2E has workload data but returns repo-centric entry points instead of service entrypoints; QA includes full API surface |
| Repository story / context | `get_repo_story`, `get_repo_context` | Works; deployment artifacts and workflow artifacts are richer | Works; service semantics, framework detection, topology story, and consumer evidence are richer | Mixed | E2E is better for raw deployment/config artifact surfacing; QA is better for curated repo/service narrative |
| File retrieval | `get_file_content("catalog-info.yaml")` | Works | Works | Tie | Both return correct content |
| Content search | `search_file_content`, `search_entity_content` | Fails with `HTTP 400: repo_id is required` when called with `repo_ids` (array) | Works; cross-repo search returns 50+ matches across 15+ repos with snippets | QA | Field-name mismatch: tool schema exposes `repo_ids` (array) but Go handler requires `repo_id` (singular string); dispatch passes raw args so key never matches |
| Infra discovery | `find_infra_resources("sample-service-api")` | Returns 1 workload match instead of infra evidence | Returns K8s resources (ConfigMap, GrafanaDashboard, GrafanaFolder, API), 2 ArgoCD ApplicationSets, 2 Crossplane XIRSARole claims | QA | E2E response is not semantically aligned with tool name |
| Deployment trace | `trace_deployment_chain("sample-service-api")` | Returns minimal (1 K8s resource, mapping_mode: "none", story: "No deployed instances found") | Returns 2 ApplicationSets, K8s resources, 11 provisioning_source_chains with terraform module detail, 12 consumer_repositories | QA | E2E trace is under-joined and materially less accurate for deployment investigation |
| Repo summary | `get_repo_summary("sample-service-api")` | Fails with `HTTP 404: repository not found` | Works; returns file counts, code entities, 8 dependents, 12 consumer_repositories with evidence_kinds, API surface, hostnames, framework_summary (Hapi/React), deployment_overview with topology_story, deployment_facts | QA | Name-based summary path is broken in E2E; QA response includes capabilities not yet designed in E2E (framework detection, topology narrative, dual consumer views) |
| Coverage summary | `get_repository_coverage(repo_id)` | Works, but only returns `entity_count`, `file_count`, `languages` | Works; returns `completeness_state`, `graph_gap_count`, `content_gap_count`, `graph_available`, `server_content_available`, timestamps, `last_error`, and full `summary` sub-object | QA | E2E exposes a reduced contract missing completeness/gap fields that operators need |
| Health / operator status | `get_index_status`, `list_ingesters` | Works for global health (896 repos, all succeeded, queue drained); `list_ingesters()` also works | Both `get_index_status` and `list_ingesters` fail (tool execution error / 500) | E2E | E2E is strictly better — QA's operator status tools are completely broken in this session |
| Code search / code analysis | `find_code`, `calculate_cyclomatic_complexity`, `analyze_code_relationships` | All fail with `HTTP 500` Neo4j syntax errors (duplicate column names, invalid comma) | All work: `find_code` returns ranked function/content matches, `calculate_cyclomatic_complexity` returns complexity scores, `analyze_code_relationships` returns caller chains with source context | QA | E2E Cypher builders are broken for overlapping code-analysis tools |
| Environment comparison | `compare_environments` | Returns "One or both environments not found" (no materialized environment data) | Times out (upstream request timeout) | Neither | Both sides broken — E2E lacks environment materialization, QA query is too expensive or unimplemented |

Three important conclusions fall out of this matrix:

- **This is not just a missing-data problem.** Several E2E tools have enough
  underlying data but expose the wrong request contract, the wrong semantic type,
  or a broken query builder.
- **E2E is already ahead in a few repo/deployment artifact areas.** The goal is
  not to copy QA blindly; it is to restore contract correctness while keeping the
  stronger raw deployment evidence that E2E already surfaces.
- **QA has capabilities with no E2E equivalent yet.** Framework detection
  (Hapi/React/Express/FastAPI), topology story synthesis, dual consumer views
  (graph-based `dependents` + content-search-based `consumer_repositories`), and
  structured `deployment_facts` with confidence thresholds are QA-only today.

### Service Query Parity

**Tools:** `resolve_entity("sample-service-api")`, `get_service_story(workload_id="workload:sample-service-api")`

| Data Point | Go E2E MCP | QA MCP |
|---|---|---|
| Workload resolution | Fails | Resolves `workload:sample-service-api` |
| Service story lookup | 404 when using qualified ID `workload:sample-service-api` (url-escapes the colon); 200 with minimal story when using plain name `sample-service-api` | Rich story returned for both forms |
| Environments surfaced | None via service MCP path | 2 (`qa`, `production`) |
| Workload instances | None via service MCP path | 2 (`qa`, `production`) |
| Public hostnames | None via service MCP path | 2 (`sample-service-api.qa.example.com`, `sample-service-api.production.example.com`) |
| API surface | None via service MCP path | 21 endpoints, `v3`, `/_specs`, `specs/index.yaml` |
| Deployment fact summary | Not available via service MCP path | `evidence_only`, medium-confidence entrypoint/environment facts |
| Service-level limitations | Not available because lookup fails | `runtime_platform_unknown`, `deployment_chain_incomplete` |

### Repository Query Parity

**Tools:** `list_indexed_repositories()`, `get_repo_story(repo_id)`, `get_repo_context(repo_id)`, `get_file_content(repo_id, "catalog-info.yaml")`

| Data Point | Go E2E MCP | QA MCP |
|---|---|---|
| Repository presence | Present as `repository:r_472ddee5` | Present as `repository:r_cd0afdc8` |
| File retrieval | Works | Works |
| Repo story | Works | Works |
| Workload count in repo story | 1 | 1 |
| Workflow relationships | `DEPLOYS_FROM` + `DISCOVERS_CONFIG_IN` to `shared-automation` | Same relationship family visible |
| Consumer repositories | 7 terraform-stack repos | Service-facing consumer set visible at service layer |
| Service-facing hostnames | Only indirectly through file content | Directly surfaced at service layer |
| API surface | Not synthesized at repo layer | Synthesized at service layer |

The key distinction is:

- **E2E is not empty.** It has the repo, the files, workflow artifacts, Docker
  artifacts, one workload, and repository consumers.
- **E2E is not service-query complete.** The workload-facing MCP path cannot yet
  return the service story that QA can.

### Consumer Detection — Currently Skewed Toward Provisioning Evidence

**Go E2E currently produces repository consumers from repo-context evidence:**
```
terraform-stack-conversation, terraform-stack-external-search,
terraform-stack-myboats, terraform-stack-poc-nlp-search,
terraform-stack-provisioning, terraform-stack-sitemaps, terraform-stack-wordsmith
```

These are useful as **deployment/config consumers**, but they are not equivalent to
the **service consumers** that operators expect when asking "who uses
sample-service-api?" They primarily reflect Terraform/module provisioning references.

**QA Python produces service-consumer evidence (via hostname + name references):**
```
sample-saved-search-api   [repo_reference, hostname_reference]
marketplace-api           [repo_reference]
traffic-reporter-api      [repo_reference]
sample-search-api         [hostname_reference: sample-service-api.qa.example.com]
provisioning-indexer-api  [repo_reference]
marketplace-automation    [hostname_reference: sample-service-api.qa/production.example.com]
sample-conversation-api   [hostname_reference: sample-service-api.qa/production.example.com]
config-service            [hostname_reference]
php-common-lib            [hostname_reference]
product-description-api   [hostname_reference]
sample-service-api-canary [hostname_reference] ← DUAL DEPLOYMENT EVIDENCE
content-indexer           [hostname_reference]
```

The dual deployment (`sample-service-api-canary`) is only visible through hostname
matching.

### Deployment Source And GitOps Evidence

Local repo inspection still proves the QA/EKS deployment path even when the E2E
service MCP path does not.

**Service repo evidence (`sample-service-api`):**
- `config/qa.json` contains `sample-service-api.qa.example.com`
- `config/production.json` contains `sample-service-api.production.example.com`
- both configs also contain ECS-related settings
- `catalog-info.yaml` declares a Backstage `API`
- `server/init/plugins/spec.js` exposes `/_specs` from `specs/index.yaml`

**GitOps repo evidence (`deployment-charts`):**
- `argocd/sample-service-api/overlays/env-qa/...` exists
- overlay values point at ECR image
  `123456789012.dkr.ecr.us-east-1.amazonaws.com/sample-service-api`
- overlay hostname is `sample-service-api.qa.svc.example.test`
- base includes `xirsarole.yaml` and dashboard resources

This means the current gap is not "the deployment evidence does not exist." The gap
is that E2E does not yet assemble or surface that evidence through the same service
investigation contract that QA does.

---

## Root Cause

### Architectural Difference

The Go data plane is primarily a **pre-computed graph model**: relationships are built
at ingestion/projection time and stored as Neo4j edges. However, the current query
layer is not graph-only. It already mixes Neo4j with repository-scoped content-store
lookups for infrastructure and deployment detail.

The QA Python instance leans further into a **query-time enrichment model**: when a
service context is requested, it performs cross-repo content searches, parses specs,
and synthesizes evidence on the fly.

The service-context gap is therefore not one single missing feature. It is the result
of several separate issues:

1. **Missing extracted signals** for service hostnames and API surface.
2. **Missing or weak derived edges** for deployment-source and consumer relationships.
3. **Query-layer enrichment that is repository-scoped today**, even where lower-level
   storage primitives already support cross-repo scans.
4. **MCP/query contract divergence** between the E2E and QA surfaces for some
   workload-facing tools.
5. **Several overlapping E2E query handlers are broken or mis-routed** rather than
   merely less enriched:
   - `find_code`, `calculate_cyclomatic_complexity`, and
     `analyze_code_relationships` fail with Neo4j syntax errors
   - `find_infra_resources` returns a workload result instead of infrastructure
     evidence
   - `get_repo_summary(repo_name)` fails on a repository that is otherwise present

### What the Go Pipeline Has

1. **39 evidence kinds** for IaC relationships (Terraform, ArgoCD, GitHub Actions, Helm, etc.)
2. **Per-generation evidence discovery** from current-repo facts plus a deferred
   backward-evidence readiness/backfill path for newly introduced repositories
3. **Regex-based matching**: patterns like `app_repo = "..."`, `github.com/org/repo`
4. **Resolution with confidence scoring** and assertion overrides
5. **PostgreSQL content store** with trigram indexes, including a storage-layer API
   that supports cross-repo file/entity search when `repo_id` is omitted
6. **Query-time enrichment already exists in parts of the Go API**, including
   repository-scoped content lookups and controller-entity aggregation from derived
   deployment source repositories
7. **Repository story/context in E2E already contains valuable deployment artifacts**:
   Dockerfiles, GitHub Actions workflows, one workload, a Kubernetes API resource,
   and terraform-stack consumer repositories are all available today

### What the Go Pipeline Lacks

1. **No hostname extraction/materialization**: config/qa.json, config/production.json,
   and similar files are stored, but service hostnames are not extracted into
   first-class evidence or graph entities
2. **No API surface extraction/materialization**: catalog-specs.yaml and related spec
   files are not parsed into service-facing routes, versions, or spec metadata
3. **No hostname-aware consumer discovery**: the existing relationship pipeline can
   backfill repo-alias evidence, but it does not discover cross-repo references to
   service hostnames or other service entrypoints
4. **No cross-repo query enrichment in the `query` package**: the storage layer
   supports optional `repo_id`, but the `query.ContentReader` used by handlers is
   still repo-scoped
5. **Deployment/controller context depends on upstream derived edges being correct**:
   controller aggregation exists, but it only sees repositories already surfaced as
   deployment sources
6. **Service-context response shape is still repository-centric**: `get_service_context`
   returns repo dependencies, repo infrastructure, and code entry points, not service
   entrypoints, API surface, or consumer evidence
7. **E2E MCP wrappers do not yet behave like QA wrappers** for the same logical tools:
   `resolve_entity` rejects the QA-shaped payload, `search_file_content` requires a
   repo identifier, and the workload story path does not yet round-trip the indexed
   repository into a service result
8. **No framework detection**: QA's `get_repo_summary` identifies runtime frameworks
   (Hapi, React, Express, FastAPI, Next.js) from code patterns and exposes them in
   `framework_summary`. E2E has no equivalent.
9. **No dual consumer view**: QA provides both graph-derived `dependents` (8 repos via
   typed edges) AND content-search-derived `consumer_repositories` (12 repos via
   hostname + name matching). E2E only has the graph-derived provisioning consumers
   (7 terraform-stack repos) which are not actual service callers.
10. **No topology story synthesis**: QA generates narrative summaries like "Top
    consumer-only repository api-node-poc-nlp-search references this service via
    hostname references..." that summarize the deployment topology for operators.
11. **`compare_environments` is unimplemented on both sides**: E2E returns "environments
    not found" (no materialized environment data), QA times out. Neither can answer
    "what differs between qa and production for this workload?"
12. **`get_repository_coverage` contract gap**: E2E returns only `entity_count`,
    `file_count`, `languages`. QA returns `completeness_state`, `graph_gap_count`,
    `content_gap_count`, `graph_available`, `server_content_available`, timestamps,
    `last_error`, and a full `summary` sub-object. Operators need the completeness
    fields to know whether a repo's data can be trusted.

---

## Evidence from Code Investigation

### PROVISIONS_DEPENDENCY_FOR is Overly Broad

**File:** `go/internal/relationships/evidence.go:54-90`

The regex patterns that trigger PROVISIONS_DEPENDENCY_FOR:
```go
// Matches ANY github.com/org/repo reference in Terraform files
Pattern: regexp.MustCompile(`(?i)github\.com[:/][^/"'\s]+/([A-Za-z0-9._-]+)(?:\.git)?`)
Confidence: 0.98

// Matches app_name = "..." in ANY Terraform file
Pattern: regexp.MustCompile(`(?i)\bapp_name\b\s*=\s*"([^"]+)"`)
Confidence: 0.94

// Matches /configd/ or /api/ path patterns
Pattern: regexp.MustCompile(`(?i)/(?:configd|api)/([A-Za-z0-9._-]+)/`)
Confidence: 0.90
```

This creates false positives: any repo mentioning a service name in a GitHub URL,
comment, or config path generates a PROVISIONS_DEPENDENCY_FOR edge.

### Cross-Repo Search Exists In Storage But Not In The Query Adapter

**Files:** `go/internal/storage/postgres/content_store.go:151-205`,
`go/internal/query/content_reader.go:163-235`

```go
func (s ContentStore) SearchFileContent(ctx, query, repoID, limit) ([]FileContentRow, error) {
    // repoID is optional — passing "" searches ALL repos
    // PostgreSQL trigram index (gin_trgm_ops) enables fast ILIKE across 896 repos
}
```

But the handler-facing query adapter is narrower:

```go
func (cr *ContentReader) SearchFileContent(ctx, repoID, pattern string, limit int) ([]FileContent, error) {
    // WHERE repo_id = $1 AND content ILIKE ...
}
```

So the underlying storage layer can do cross-repo search, but the query package does
not currently expose that capability to `get_service_context` or
`trace_deployment_chain`.

The Postgres schema still supports the broader search:
```sql
CREATE INDEX content_files_content_trgm_idx
    ON content_files USING gin (content gin_trgm_ops);
```

This means the ADR should treat cross-repo consumer search as a real query-layer
implementation project, not just a small wiring task.

### Backward Evidence Exists, But Not For Hostname-Level Service Discovery

**Files:** `go/internal/reducer/cross_repo_resolution.go:88-123`,
`go/internal/storage/postgres/ingestion.go:588-631`

The reducer still resolves evidence per generation:
```go
evidenceFacts := h.EvidenceLoader.ListEvidenceFacts(ctx, generationID)
```

But the system is not purely forward-only anymore. Cross-repo resolution is gated on
`GraphProjectionPhaseBackwardEvidenceCommitted`, and ingestion performs a corpus-wide
re-discovery/backfill for newly introduced target repositories.

The real limitation is narrower:

- backward-style repo-alias evidence exists
- hostname/service-entrypoint evidence does not
- therefore consumer discovery remains inaccurate for services whose best evidence is
  hostname usage rather than repository alias references

---

## Options

### Option A: Query-Time Enrichment (Python Parity)

Add cross-repo content search to the Go query layer at request time.

**Implementation:**
1. Extend the `query` package with a cross-repo content-search adapter instead of
   relying on the current repo-scoped `ContentReader`
2. `get_service_context` queries content store for hostname patterns across all repos
3. `trace_deployment_chain` uses the same adapter for consumer discovery and
   optional provenance lookup
4. Parse OpenAPI specs on demand
5. Synthesize service entrypoints and consumer evidence directly in the response

This option should not be described as "search deployment-charts repo" because the current
query layer already knows how to aggregate ArgoCD controller entities from derived
deployment source repositories. The gap is getting the right deployment source repos
and service-entrypoint evidence into that path.

**Pros:**
- Exact parity with QA Python behavior
- No schema changes required
- Leverages existing trigram indexes

**Cons:**
- Query latency increases from ~50ms to 1-3s
- No audit trail for dynamically discovered evidence
- Repeated computation on every request
- Harder to debug "why does this relationship exist?"

### Option B: Ingestion-Time Enrichment (Materialized at Write)

Extend the ingestion pipeline to extract hostnames, parse OpenAPI specs, and compute
backward references at ingestion time. Store as evidence facts and resolve into graph edges.

**Implementation:**
1. New evidence kinds for service entrypoints and cross-repo usage, for example:
   `CONFIG_HOSTNAME_REFERENCE`, `OPENAPI_SERVER_URL`, `HOSTNAME_CONSUMER_REFERENCE`
2. New extractor: parse `config/*.json` for hostname patterns during ingestion
3. New extractor: parse OpenAPI specs for endpoints + server URLs
4. New backward discovery: when repo A is ingested, search all repos' content for
   references to repo A's hostnames or emitted service entrypoints
5. Materialize service-facing query data so `get_service_context` stops falling back
   to repository-only entry points
6. Store as `relationship_evidence_facts` and/or service-specific materialized
   entities, then resolve into graph edges

**Pros:**
- Sub-100ms query latency (everything pre-computed)
- Full audit trail (evidence_id, confidence, rationale)
- Assertion overrides work (humans can reject false positives)
- Consistent with existing architecture

**Cons:**
- Higher ingestion cost per repo (cross-repo search during commit)
- Requires re-ingestion to populate existing repos
- More complex evidence lifecycle (stale hostname evidence when configs change)
- Larger Neo4j graph (more edges)

### Option C: Hybrid — Materialized Core + Query-Time Enrichment

Pre-compute the high-value, stable data at ingestion time. Provide query-time
enrichment for expensive or volatile data behind an `?enrich=true` parameter.

**Materialized at ingestion (fast path):**
- Hostname extraction from config files -> service-entrypoint evidence/entities
- OpenAPI spec parsing -> API surface entities stored in graph
- Tighten deployment-source derivation so existing controller aggregation sees the
  right source repositories
- Service-context response shape updated to prefer service-facing entrypoints over
  repository `main` functions

**Query-time enrichment (slow path, opt-in):**
- Cross-repo consumer search (hostname + name pattern matching)
- Provisioning source chain construction (follow terraform modules)
- Documentation/support overview generation
- Rich story narrative synthesis

**Pros:**
- Fast default queries with pre-computed relationships
- Rich opt-in queries for deep investigation
- Clear separation: graph = truth, enrichment = derived
- Incremental: ship fast path first, enrichment later

**Cons:**
- Two code paths to maintain
- Client must know about `?enrich=true`
- Potential inconsistency between fast/enriched results

---

## Decision

**Recommended: Option C (Hybrid) with Option B as the end state.**

This ADR should also be treated as the contract-fix plan for the overlapping QA and
E2E MCP tools, not just the enrichment plan for the service query layer.

### Rationale

1. **Immediate value** comes from restoring accuracy in identity, relationship
   mapping, and diagnosis paths, not from treating the problem as cosmetic service
   enrichment. The first step is to separate:
   - incorrect or missing service signals
   - incorrect or missing deployment-source derivation
   - repo-scoped versus cross-repo query limitations
   - MCP contract divergence between E2E and QA
   - broken handlers that currently fail even when the underlying data exists

2. **Medium-term** add hostname extraction and service-facing materialization so the
   default service context becomes structurally useful without expensive ad hoc scans.

3. **Selective query-time enrichment** still makes sense for consumer discovery and
   deep provenance, but it should be treated as an explicit secondary path built on a
   query adapter that can safely do cross-repo scans.

4. **Long-term** migrate high-volume query-time enrichments into materialized service
   facts once their semantics stabilize.

All phases below are important. The sequencing reflects **dependency order and
trust-building order**, not importance. `P0` is first because the rest of the
system cannot be trusted until identity resolution, relationship lookup, and core
contract behavior are correct.

### Phase Plan

| Phase | Scope | Timeline |
|---|---|---|
| **P0: Accuracy And Contract Blockers** | Fix MCP/query-path correctness and core relationship mapping: (1) `resolve_entity` dispatch maps `query`→body but API expects `name` field; (2) `get_service_story` and `get_service_context` preserve qualified IDs like `workload:sample-service-api`; (3) `search_file_content` field-name mismatch — tool schema exposes `repo_ids` (array) but handler requires `repo_id` (singular); also allow cross-repo when omitted; (4) fix Cypher duplicate-column / malformed-query bugs in `find_code`, `calculate_cyclomatic_complexity`, `analyze_code_relationships`, and `execute_language_query`; (5) make `find_infra_resources` return actual infra resources rather than workload stubs; (6) make `get_repo_summary(repo_name)` resolve existing repos; (7) K8s resource `kind` field is not NULL in projector; (8) stop presenting repo `main` functions as service entrypoints | 3-5 days |
| **P1: Service Signal Materialization** | Hostname extraction from `config/*.json` and materialized service-entrypoint evidence/entities | 3-5 days |
| **P2: Cross-Repo Consumer Accuracy** | Add a cross-repo search adapter to the query layer and implement opt-in consumer enrichment so service callers are not confused with provisioning/config consumers; retain the dual view of graph `dependents` plus content-search `consumer_repositories` | 4-7 days |
| **P3: API Surface Accuracy** | OpenAPI spec parsing -> API surface entities and service-context response fields | 1 week |
| **P4: Deployment Provenance Accuracy** | Tighten deployment-source derivation and controller provenance so existing ArgoCD aggregation returns the right repos/entities | 1 week |
| **P5: Environment And Coverage Contract Completion** | `get_repository_coverage` returns completeness/gap/timestamp fields needed by operators; `compare_environments` moves from "not found/timeout" behavior to either implemented environment diffs or an explicit not-yet-supported contract | 1 week |
| **P6: Provisioning Chain Accuracy** | Provisioning source chain construction and ranking | 1 week |
| **P7: Operator Narrative And Framework Enrichment** | Story/documentation/framework enrichment: topology story synthesis, framework detection (Hapi/React/Express/FastAPI), and documentation overview generation after service facts and consumer evidence are trustworthy | 1 week |

---

## Consequences

### Positive
- Service context becomes useful for operators (environments, endpoints, consumers visible)
- Dual deployment patterns become discoverable (hostname-based matching)
- MCP tools return actionable intelligence instead of structural data
- Parity with QA Python for the critical service investigation workflow

### Negative
- Query latency increases for enriched queries (mitigated by caching)
- Ingestion time increases slightly for hostname/spec extraction
- More complex evidence lifecycle (hostname evidence can go stale)
- Need to re-ingest 896 repos to populate new evidence types

### Risks
- Cross-repo trigram search at 896 repos may hit performance limits for common patterns
- False positive consumer detection (e.g., "boats" matching unrelated repos)
- OpenAPI spec parsing complexity (multiple formats, $ref resolution)

### Mitigations
- Index hostname patterns in a materialized view for O(1) lookup
- Use confidence scoring to rank consumer evidence (hostname > name substring)
- Start with simple OpenAPI parsing (paths/methods only, no $ref resolution)
- Cache enrichment results with TTL tied to content store freshness

---

## Appendix: Evidence Comparison Data

### QA Python Service Context Response (sample-service-api)

```json
{
  "instances": [
    {"id": "workload-instance:sample-service-api:qa", "environment": "qa"},
    {"id": "workload-instance:sample-service-api:production", "environment": "production"}
  ],
  "entrypoints": [
    {"hostname": "sample-service-api.qa.example.com", "environment": "qa", "visibility": "public"},
    {"hostname": "sample-service-api.production.example.com", "environment": "production", "visibility": "public"}
  ],
  "api_surface": {
    "endpoint_count": 21,
    "api_versions": ["v3"],
    "docs_routes": ["/_specs"],
    "spec_files": [{"relative_path": "specs/index.yaml", "discovered_from": "server/init/plugins/spec.js"}],
    "endpoints": [
      {"path": "/v3", "methods": ["get", "post", "delete"], "operation_ids": ["search", "postSearch", "deleteSearchScroll"]},
      {"path": "/v3/multiSearch", "methods": ["get", "post"], "operation_ids": ["multiSearch", "postMultiSearch"]},
      {"path": "/v3/cities", "methods": ["get"], "operation_ids": ["getCities"]},
      {"path": "/v3/listing/{id}", "methods": ["get"], "operation_ids": ["getListing"]},
      "... 17 more endpoints"
    ]
  },
  "observed_config_environments": ["qa", "production"],
  "coverage": {"completeness_state": "complete", "functions": 384, "content_entity_count": 3191}
}
```

### QA MCP Service Story Response (sample-service-api)

```json
{
  "subject": {"id": "workload:sample-service-api", "kind": "service", "name": "sample-service-api"},
  "story": [
    "sample-service-api has 2 known workload instances across environments.",
    "Owned by repositories sample-service-api.",
    "Public entrypoints: sample-service-api.production.example.com, sample-service-api.qa.example.com."
  ],
  "deployment_overview": {
    "instances": [
      {"id": "workload-instance:sample-service-api:qa", "environment": "qa"},
      {"id": "workload-instance:sample-service-api:production", "environment": "production"}
    ],
    "hostnames": [
      {"hostname": "sample-service-api.production.example.com", "environment": "production"},
      {"hostname": "sample-service-api.qa.example.com", "environment": "qa"}
    ],
    "api_surface": {
      "endpoint_count": 21,
      "api_versions": ["v3"],
      "docs_routes": ["/_specs"]
    }
  }
}
```

### Go E2E MCP Service Story Result (sample-service-api)

```text
HTTP 404: {"detail":"service not found","error":"Not Found"}
```

### Go E2E Repository Story / Context (sample-service-api)

```json
{
  "repository": {"id": "repository:r_472ddee5", "name": "sample-service-api"},
  "story": "Repository sample-service-api contains 537 indexed files. Defines 1 workload(s): sample-service-api.",
  "workflow_relationships": [
    {"type": "DEPLOYS_FROM", "target_name": "shared-automation", "evidence_type": "github_actions_reusable_workflow_ref"},
    {"type": "DISCOVERS_CONFIG_IN", "target_name": "shared-automation", "evidence_type": "github_actions_workflow_input_repository"}
  ],
  "consumer_repositories": [
    "terraform-stack-conversation",
    "terraform-stack-external-search",
    "terraform-stack-myboats",
    "terraform-stack-poc-nlp-search",
    "terraform-stack-provisioning",
    "terraform-stack-sitemaps",
    "terraform-stack-wordsmith"
  ]
}
```

### QA Python Consumer Evidence (sample)

```json
{
  "repository": "sample-saved-search-api",
  "repo_id": "repository:r_0a6c413b",
  "evidence_kinds": ["repository_reference", "hostname_reference"],
  "matched_values": ["sample-service-api", "sample-service-api.qa.example.com"],
  "sample_paths": ["sample-saved-search.ts", "config/local.json", "server/init/plugins/sample-service-api-batch.js"]
}
```

### Go E2E Consumer Evidence (what exists today)

```json
// Via repository context / provisioning-style evidence — useful, but not equivalent
// to service-consumer evidence
[
  {"consumer": "terraform-stack-conversation", "consumer_id": "repository:r_4a0e4b73"},
  {"consumer": "terraform-stack-external-search", "consumer_id": "repository:r_a6d882eb"},
  "... 5 more terraform-stack-* repos"
]
```

### GitOps Evidence Proven By Repo Inspection

```json
{
  "service_repo": {
    "hostnames": [
      {"path": "config/qa.json", "value": "sample-service-api.qa.example.com"},
      {"path": "config/production.json", "value": "sample-service-api.production.example.com"}
    ],
    "spec_route": {"path": "server/init/plugins/spec.js", "spec_file": "specs/index.yaml", "docs_route": "/_specs"}
  },
  "helm_charts_repo": {
    "argocd_overlay": "argocd/sample-service-api/overlays/env-qa",
    "image_repository": "123456789012.dkr.ecr.us-east-1.amazonaws.com/sample-service-api",
    "service_hostname": "sample-service-api.qa.svc.example.test",
    "base_resources": ["xirsarole.yaml", "dashboard-overview.yaml", "folder.yaml"]
  }
}
```

### ArgoCD Evidence (QA service narrative)

```json
{
  "argocd_applicationsets": [
    {
      "app_name": "sample-service-api",
      "project": "{{.argocd.project}}",
      "dest_namespace": "{{.helm.namespace}}",
      "source_repos": "https://github.com/example-org/deployment-charts",
      "source_roots": "argocd/sample-service-api/"
    },
    {
      "app_name": "dashboard-sample-service-api",
      "project": "monitoring",
      "dest_namespace": "monitoring",
      "source_repos": "https://github.com/example-org/deployment-charts",
      "source_roots": "argocd/sample-service-api/"
    }
  ]
}
```

---

## Appendix: Code Architecture References

### Evidence Discovery Pipeline
- Entry: `go/internal/storage/postgres/ingestion.go:317` — `DiscoverEvidence()` called during commit
- Discovery: `go/internal/relationships/evidence.go:16-194` — Pattern matching against catalog
- Catalog: `go/internal/storage/postgres/ingestion.go:553-586` — Loads all repo aliases
- Storage: `go/internal/storage/postgres/relationship_store.go:134-181` — Upserts to relationship_evidence_facts

### Resolution Pipeline
- Handler: `go/internal/reducer/cross_repo_resolution.go:59-231` — Loads evidence, resolves, writes edges
- Resolver: `go/internal/relationships/resolver.go:62-95` — Confidence aggregation + assertions
- Neo4j: `go/internal/storage/neo4j/canonical_relationships.go:19-61` — Typed edge MERGE

### Query Layer
- Service context: `go/internal/query/entity.go:376-465` — workload fetch plus
  repository-scoped dependency/infrastructure/entry-point enrichment
- Deployment chain: `go/internal/query/impact_trace_deployment.go:18-70` — Neo4j + single-repo content
- Query adapter: `go/internal/query/content_reader.go:163-235` — repo-scoped file/entity search only
- Storage search: `go/internal/storage/postgres/content_store.go:151-205` — supports cross-repo when `repo_id` is omitted

### Untapped Infrastructure
- Trigram index: `content_files_content_trgm_idx` using `gin (content gin_trgm_ops)` — fast cross-repo ILIKE
- Entity search: `content_entities_source_trgm_idx` using `gin (source_cache gin_trgm_ops)`
- Both support cross-repo search when repo_id parameter is omitted
