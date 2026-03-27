# Canonical Platform Entities and Runtime Context Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the canonical relationship system from repo-to-repo edges into entity-aware runtime modeling so PlatformContextGraph can resolve `Repository`, `Platform`, and `WorkloadSubject` relationships canonically, project them into Neo4j, and answer end-to-end repository questions truthfully across ECS, EKS, Terraform, Helm, Kustomize, and ArgoCD.

**Architecture:** Keep Postgres as the source of truth for evidence, assertions, candidates, resolved generations, and canonical entities. Add a generalized entity registry plus entity-aware resolver/projection logic, then roll the widened model into repository query surfaces, MCP/API contracts, and acceptance coverage without regressing current JSON logging, OTEL tracing, or partial-coverage truthfulness.

**Tech Stack:** Python, PostgreSQL/psycopg, Neo4j Cypher, pytest, Docker Compose, OpenTelemetry, structured JSON logging

---

## File Structure

### Existing files to modify

- `src/platform_context_graph/relationships/models.py`
  - widen repository-only dataclasses into entity-aware models while preserving checkout support
- `src/platform_context_graph/relationships/postgres_support.py`
  - add additive schema for `relationship_entities` plus entity-aware columns on evidence/candidate/resolved/assertion tables
- `src/platform_context_graph/relationships/postgres_generation.py`
  - persist entity registry rows and entity-aware generation records
- `src/platform_context_graph/relationships/postgres.py`
  - expose entity-aware persistence and read APIs without breaking current store usage
- `src/platform_context_graph/relationships/file_evidence.py`
  - orchestrate portable extractor modules and keep the top-level file small
- `src/platform_context_graph/relationships/file_evidence_support.py`
  - add catalog matching helpers for platform/workload subject candidates and portable locator extraction
- `src/platform_context_graph/relationships/resolver.py`
  - resolve typed edges across mixed entity families and derive compatibility `DEPENDS_ON`
- `src/platform_context_graph/relationships/execution.py`
  - build entity-aware evidence, projection, logging, and tracing
- `src/platform_context_graph/query/repositories/context_data.py`
  - aggregate canonical entity relationships back into repository-centered context
- `src/platform_context_graph/query/repositories/stats_data.py`
  - surface the new coverage/platform/deployment counts and limitations
- `src/platform_context_graph/query/repositories/coverage_data.py`
  - keep completeness-state/gap logic reusable across summary, stats, and context outputs
- `src/platform_context_graph/mcp/tools/handlers/ecosystem.py`
  - align MCP summary output with the widened repo summary/context contracts
- `src/platform_context_graph/prompts.py`
  - update truthfulness guidance for runtime platform, DNS, and entrypoint limitations
- `src/platform_context_graph/indexing/coordinator_coverage.py`
  - preserve truthful gap fields while query/MCP outputs start depending on them more directly
- `docker-compose.yaml`
  - verify runtime env propagation remains correct for parse-worker and queue-depth controls
- `docker-compose.template.yml`
  - keep generated compose template aligned with runtime env behavior
- `docs/docs/reference/relationship-mapping.md`
  - document new canonical entity vocabulary and typed platform chains
- `src/platform_context_graph/relationships/README.md`
  - document how to add future portable mappings safely

### New files to create

- `src/platform_context_graph/relationships/entities.py`
  - canonical entity dataclasses, identity helpers, and normalization rules for `Repository`, `Platform`, and `WorkloadSubject`
- `src/platform_context_graph/relationships/evidence_terraform.py`
  - Terraform/Terragrunt platform and dependency evidence extraction
- `src/platform_context_graph/relationships/evidence_gitops.py`
  - ArgoCD/Helm/Kustomize deploy/config/runtime evidence extraction
- `src/platform_context_graph/relationships/platform_resolution.py`
  - entity resolution and typed derivation helpers for platform/workload subject candidates
- `src/platform_context_graph/query/repositories/relationship_summary.py`
  - reusable assembly helpers for `get_repo_summary`, `get_repository_stats`, and `get_repository_context`
- `tests/unit/relationships/test_entities.py`
  - unit coverage for entity IDs, uniqueness normalization, and platform safety rules
- `tests/unit/relationships/test_platform_resolution.py`
  - unit coverage for mixed-entity typed resolution and compatibility derivation
- `tests/unit/relationships/test_postgres_store.py`
  - unit coverage for additive entity migration, backfill-safe reads, and generation activation safety
- `tests/unit/query/test_repository_runtime_context.py`
  - unit coverage for repository-centered runtime/deployment summaries and limitations
- `tests/integration/mcp/test_repository_runtime_context.py`
  - integration coverage for MCP-facing repo summary/context truthfulness
- `tests/integration/runtime/test_compose_env_contract.py`
  - integration coverage for parse-worker and queue-depth compose env propagation
- `tests/fixtures/ecosystems/platform_runtime_corpus/`
  - portable ECS/EKS/Terraform/Helm/Kustomize/ArgoCD fixtures for acceptance-oriented tests

## Chunk 1: Canonical Entities and Entity-Aware Resolution

### Task 1: Add canonical entity primitives and safety rules

**Files:**
- Create: `src/platform_context_graph/relationships/entities.py`
- Modify: `src/platform_context_graph/relationships/models.py`
- Test: `tests/unit/relationships/test_entities.py`

- [ ] **Step 1: Write the failing entity identity tests**

```python
from platform_context_graph.relationships.entities import (
    CanonicalEntity,
    PlatformEntity,
    WorkloadSubjectEntity,
    canonical_platform_id,
)


def test_canonical_platform_id_requires_stable_discriminator() -> None:
    assert canonical_platform_id(
        kind="eks",
        provider="aws",
        name=None,
        environment=None,
        region=None,
        locator=None,
    ) is None


def test_canonical_platform_id_prefers_locator_over_name() -> None:
    assert (
        canonical_platform_id(
            kind="ecs",
            provider="aws",
            name="ignored-name",
            environment="prod",
            region="us-east-1",
            locator="arn:aws:ecs:us-east-1:123456789012:cluster/node10",
        )
        == "platform:ecs:aws:arn:aws:ecs:us-east-1:123456789012:cluster/node10:prod:us-east-1"
    )


def test_workload_subject_id_normalizes_repo_type_name_environment_and_path() -> None:
    entity = WorkloadSubjectEntity.from_parts(
        repository_id="repository:r_1234abcd",
        subject_type="addon",
        name="Grafana",
        environment="ops-qa",
        path="argocd/grafana/overlays/ops-qa",
    )
    assert entity.entity_id == (
        "workload-subject:repository:r_1234abcd:addon:grafana:ops-qa:"
        "argocd/grafana/overlays/ops-qa"
    )
```

- [ ] **Step 2: Run the entity tests to verify they fail**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_entities.py -q`

Expected: FAIL with missing module, missing helpers, or assertion failures for unsafe platform IDs.

- [ ] **Step 3: Implement the entity helpers**

```python
@dataclass(slots=True, frozen=True)
class PlatformEntity:
    entity_id: str
    kind: str
    provider: str | None
    name: str | None
    environment: str | None
    region: str | None
    locator: str | None
    details: dict[str, Any] = field(default_factory=dict)


def canonical_platform_id(
    *,
    kind: str,
    provider: str | None,
    name: str | None,
    environment: str | None,
    region: str | None,
    locator: str | None,
) -> str | None:
    discriminator = normalize(locator) or normalize(name)
    if discriminator is None and not (normalize(environment) and normalize(region)):
        return None
    return (
        "platform:"
        f"{normalize(kind) or 'none'}:"
        f"{normalize(provider) or 'none'}:"
        f"{discriminator or 'none'}:"
        f"{normalize(environment) or 'none'}:"
        f"{normalize(region) or 'none'}"
    )
```

- [ ] **Step 4: Run the entity tests to verify they pass**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_entities.py -q`

Expected: PASS

- [ ] **Step 5: Commit the entity foundation**

```bash
git add src/platform_context_graph/relationships/entities.py \
  src/platform_context_graph/relationships/models.py \
  tests/unit/relationships/test_entities.py
git commit -m "feat: add canonical relationship entities"
```

### Task 2: Widen the Postgres schema and store APIs additively

**Files:**
- Modify: `src/platform_context_graph/relationships/postgres_support.py`
- Modify: `src/platform_context_graph/relationships/postgres_generation.py`
- Modify: `src/platform_context_graph/relationships/postgres.py`
- Test: `tests/unit/relationships/test_postgres_store.py`
- Test: `tests/unit/relationships/test_resolver.py`

- [ ] **Step 1: Write failing persistence tests for entity-aware rows**

```python
def test_replace_generation_persists_relationship_entities(monkeypatch) -> None:
    store = PostgresRelationshipStore("postgresql://example")
    generation = store.replace_generation(
        scope="repo_dependencies",
        run_id="run-123",
        checkouts=[],
        entities=[
            PlatformEntity(
                entity_id="platform:ecs:aws:cluster/node10:prod:us-east-1",
                kind="ecs",
                provider="aws",
                name="node10",
                environment="prod",
                region="us-east-1",
                locator="cluster/node10",
            )
        ],
        evidence_facts=[],
        candidates=[],
        resolved=[],
    )
    assert generation.generation_id.startswith("generation_")


def test_existing_repo_backed_generation_remains_readable_until_entity_cutover(
    monkeypatch,
) -> None:
    store = PostgresRelationshipStore("postgresql://example")
    active = store.get_active_generation(scope="repo_dependencies")
    assert active is not None


def test_backfill_populates_entity_ids_for_existing_repo_backed_rows(monkeypatch) -> None:
    row = {
        "source_repo_id": "repository:r_source",
        "target_repo_id": "repository:r_target",
        "source_entity_id": None,
        "target_entity_id": None,
    }
    assert entity_or_repo_identity(row, "source") == "repository:r_source"
    assert entity_or_repo_identity(row, "target") == "repository:r_target"


def test_failed_projection_preserves_last_known_good_active_generation(monkeypatch) -> None:
    active_before = ResolutionGeneration(
        generation_id="generation_active",
        scope="repo_dependencies",
        run_id="run-1",
        status="active",
    )
    active_after = preserve_active_generation_on_projection_failure(
        active_before=active_before,
        projection_error=RuntimeError("missing Platform node"),
    )
    assert active_after.generation_id == "generation_active"
```

- [ ] **Step 2: Run the targeted persistence tests to verify they fail**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_postgres_store.py tests/unit/relationships/test_resolver.py -q`

Expected: FAIL because `replace_generation` and schema helpers do not accept entity rows yet.

- [ ] **Step 3: Implement additive schema and persistence**

```python
CREATE TABLE IF NOT EXISTS relationship_entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    repository_id TEXT,
    subject_type TEXT,
    kind TEXT,
    provider TEXT,
    name TEXT NOT NULL,
    environment TEXT,
    path TEXT,
    region TEXT,
    locator TEXT,
    details JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

ALTER TABLE relationship_evidence_facts
    ADD COLUMN IF NOT EXISTS source_entity_id TEXT,
    ADD COLUMN IF NOT EXISTS target_entity_id TEXT;
```

- [ ] **Step 4: Add backfill-safe reads and rollback-safe activation**

Implement store logic so:

```python
source_entity_id = fact.source_entity_id or repository_entity_id(fact.source_repo_id)
target_entity_id = fact.target_entity_id or repository_entity_id(fact.target_repo_id)
```

and keep repo-backed reads working until Chunk 2 switches query surfaces.

Also prove the migration contract with one focused helper:

```python
def entity_or_repo_identity(row: Mapping[str, Any], side: str) -> str:
    return row.get(f"{side}_entity_id") or repository_entity_id(row[f"{side}_repo_id"])
```

and keep active-generation rollback safe:

```python
if projection_validation_failed:
    return fetch_active_generation(scope=scope)
```

- [ ] **Step 5: Run the targeted persistence tests to verify they pass**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_postgres_store.py tests/unit/relationships/test_resolver.py -q`

Expected: PASS

- [ ] **Step 6: Commit the additive schema work**

```bash
git add src/platform_context_graph/relationships/postgres_support.py \
  src/platform_context_graph/relationships/postgres_generation.py \
  src/platform_context_graph/relationships/postgres.py \
  tests/unit/relationships/test_postgres_store.py \
  tests/unit/relationships/test_resolver.py
git commit -m "feat: persist canonical relationship entities"
```

### Task 3: Resolve typed relationships across repositories, platforms, and workload subjects

**Files:**
- Create: `src/platform_context_graph/relationships/platform_resolution.py`
- Modify: `src/platform_context_graph/relationships/resolver.py`
- Modify: `src/platform_context_graph/relationships/models.py`
- Test: `tests/unit/relationships/test_platform_resolution.py`
- Test: `tests/unit/relationships/test_resolver.py`

- [ ] **Step 1: Write failing mixed-entity resolution tests**

```python
def test_platform_chain_derives_depends_on_from_runs_on_and_provisions_platform() -> None:
    candidates, resolved = resolve_entity_relationships(
        evidence_facts=[
            RelationshipEvidenceFact(
                evidence_kind="TERRAFORM_ECS_CLUSTER",
                relationship_type="PROVISIONS_PLATFORM",
                source_entity_id="repository:terraform-stack-ecs",
                target_entity_id="platform:ecs:aws:cluster/node10:prod:us-east-1",
                confidence=0.99,
                rationale="Terraform provisions ECS cluster node10",
            ),
            RelationshipEvidenceFact(
                evidence_kind="TERRAFORM_ECS_SERVICE",
                relationship_type="RUNS_ON",
                source_entity_id="repository:api-node-boats",
                target_entity_id="platform:ecs:aws:cluster/node10:prod:us-east-1",
                confidence=0.97,
                rationale="Service binds to ECS cluster node10",
            ),
        ],
        assertions=[],
    )
    assert ("repository:api-node-boats", "platform:ecs:aws:cluster/node10:prod:us-east-1", "RUNS_ON") in {
        (item.source_entity_id, item.target_entity_id, item.relationship_type)
        for item in resolved
    }
    assert ("repository:api-node-boats", "repository:terraform-stack-ecs", "DEPENDS_ON") in {
        (item.source_entity_id, item.target_entity_id, item.relationship_type)
        for item in resolved
    }
```

- [ ] **Step 2: Run the mixed-entity resolver tests to verify they fail**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_platform_resolution.py tests/unit/relationships/test_resolver.py -q`

Expected: FAIL because resolver code is still repo-only.

- [ ] **Step 3: Implement entity-aware resolution helpers**

```python
def derive_compatibility_depends_on(
    resolved: Sequence[ResolvedRelationship],
    rejections: set[tuple[str, str, str]],
) -> list[ResolvedRelationship]:
    # direct typed derivations
    # chain derivation: RUNS_ON + PROVISIONS_PLATFORM => service DEPENDS_ON infra repo
```

and keep the typed-first suppression rule:

```python
if has_typed_edge_for_pair(source_entity_id, target_entity_id):
    suppress_generic_depends_on_candidate(...)
```

- [ ] **Step 4: Run the mixed-entity resolver tests to verify they pass**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_platform_resolution.py tests/unit/relationships/test_resolver.py -q`

Expected: PASS

- [ ] **Step 5: Commit the entity-aware resolver**

```bash
git add src/platform_context_graph/relationships/platform_resolution.py \
  src/platform_context_graph/relationships/resolver.py \
  src/platform_context_graph/relationships/models.py \
  tests/unit/relationships/test_platform_resolution.py \
  tests/unit/relationships/test_resolver.py
git commit -m "feat: resolve canonical platform and workload relationships"
```

### Task 4: Expand evidence extraction and graph projection for canonical entities

**Files:**
- Create: `src/platform_context_graph/relationships/evidence_terraform.py`
- Create: `src/platform_context_graph/relationships/evidence_gitops.py`
- Modify: `src/platform_context_graph/relationships/file_evidence.py`
- Modify: `src/platform_context_graph/relationships/file_evidence_support.py`
- Modify: `src/platform_context_graph/relationships/execution.py`
- Modify: `src/platform_context_graph/tools/graph_builder_platforms.py`
- Test: `tests/unit/relationships/test_file_evidence.py`
- Test: `tests/unit/relationships/test_platform_resolution.py`

- [ ] **Step 1: Write failing extraction/projection tests for ECS, EKS, and Kustomize**

```python
def test_terraform_ecs_evidence_emits_provisions_platform_and_runs_on() -> None:
    evidence = discover_checkout_file_evidence([ecs_checkout, service_checkout])
    assert ("PROVISIONS_PLATFORM", "TERRAFORM_ECS_CLUSTER") in {
        (item.relationship_type, item.evidence_kind) for item in evidence
    }
    assert ("RUNS_ON", "TERRAFORM_ECS_SERVICE") in {
        (item.relationship_type, item.evidence_kind) for item in evidence
    }


def test_kustomize_overlay_evidence_emits_deploys_from_without_patch_noise() -> None:
    evidence = discover_checkout_file_evidence([overlay_checkout, service_checkout])
    assert any(item.relationship_type == "DEPLOYS_FROM" for item in evidence)
    assert not any(item.evidence_kind == "PATCHES" for item in evidence)


def test_argocd_eks_evidence_emits_discovers_config_in_and_deploys_from() -> None:
    evidence = discover_checkout_file_evidence(
        [argocd_checkout, observability_checkout, helm_checkout]
    )
    assert ("DISCOVERS_CONFIG_IN", "ARGOCD_APPLICATIONSET_DISCOVERY") in {
        (item.relationship_type, item.evidence_kind) for item in evidence
    }
    assert ("DEPLOYS_FROM", "ARGOCD_APPLICATIONSET_DEPLOY_SOURCE") in {
        (item.relationship_type, item.evidence_kind) for item in evidence
    }


def test_argocd_runtime_evidence_emits_runs_on_for_explicit_eks_target() -> None:
    evidence = discover_checkout_file_evidence(
        [argocd_checkout, observability_checkout, helm_checkout]
    )
    assert ("RUNS_ON", "ARGOCD_DESTINATION_PLATFORM") in {
        (item.relationship_type, item.evidence_kind) for item in evidence
    }
```

- [ ] **Step 2: Run the extraction tests to verify they fail**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_file_evidence.py tests/unit/relationships/test_platform_resolution.py -q`

Expected: FAIL because the extractor still emits repo-only facts and incomplete ECS/EKS/Kustomize semantics.

- [ ] **Step 3: Implement portable platform/runtime evidence**

Add extractor logic for:

```python
if explicit_ecs_resource and cluster_name:
    emit("PROVISIONS_PLATFORM", source=infra_repo, target=platform_entity)

if ecs_service_module and app_repo_match:
    emit("RUNS_ON", source=service_repo, target=platform_entity)

if kustomize_remote_resource or helm_block identifies source repo:
    emit("DEPLOYS_FROM", source=deployable_repo_or_subject, target=source_repo)

if applicationset_repo_url and discovery_files_path:
    emit("DISCOVERS_CONFIG_IN", source=argocd_repo, target=config_repo)

if applicationset_source_repo_url or helm_repo_reference:
    emit("DEPLOYS_FROM", source=deployable_repo_or_subject, target=source_repo)

if destination_cluster_name or explicit_eks_platform_signal:
    emit("RUNS_ON", source=deployable_repo_or_subject, target=platform_entity)
```

Keep file responsibilities narrow:

- `evidence_terraform.py`
  - Terraform/Terragrunt extraction only
- `evidence_gitops.py`
  - ArgoCD/Helm/Kustomize extraction only
- `file_evidence.py`
  - orchestration and dedupe only

- [ ] **Step 4: Update graph projection to support entity nodes**

Project canonical nodes and edges:

```cypher
MERGE (p:Platform {id: row.entity_id})
SET p.kind = row.kind, p.provider = row.provider, p.environment = row.environment

MERGE (w:WorkloadSubject {id: row.entity_id})
SET w.name = row.name, w.subject_type = row.subject_type
```

while retaining derived compatibility `DEPENDS_ON` for repository-centered queries.

- [ ] **Step 5: Run the extraction/projection tests to verify they pass**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_file_evidence.py tests/unit/relationships/test_platform_resolution.py tests/unit/relationships/test_resolver.py -q`

Expected: PASS

- [ ] **Step 6: Commit the extractor and projection work**

```bash
git add src/platform_context_graph/relationships/file_evidence.py \
  src/platform_context_graph/relationships/evidence_terraform.py \
  src/platform_context_graph/relationships/evidence_gitops.py \
  src/platform_context_graph/relationships/file_evidence_support.py \
  src/platform_context_graph/relationships/execution.py \
  src/platform_context_graph/tools/graph_builder_platforms.py \
  tests/unit/relationships/test_file_evidence.py \
  tests/unit/relationships/test_platform_resolution.py \
  tests/unit/relationships/test_resolver.py
git commit -m "feat: project canonical platform runtime relationships"
```

- [ ] **Step 7: Run the combined Chunk 1 verification suite**

Run:

```bash
PYTHONPATH=src uv run --extra dev python -m pytest \
  tests/unit/relationships/test_entities.py \
  tests/unit/relationships/test_postgres_store.py \
  tests/unit/relationships/test_platform_resolution.py \
  tests/unit/relationships/test_file_evidence.py \
  tests/unit/relationships/test_resolver.py -q
```

Expected: PASS

## Chunk 2: Query Surfaces, MCP Truthfulness, and Acceptance Coverage

### Task 5: Add repository-centered runtime/deployment summary helpers

**Files:**
- Create: `src/platform_context_graph/query/repositories/relationship_summary.py`
- Modify: `src/platform_context_graph/query/repositories/context_data.py`
- Modify: `src/platform_context_graph/query/repositories/stats_data.py`
- Modify: `src/platform_context_graph/query/repositories/coverage_data.py`
- Test: `tests/unit/query/test_repository_runtime_context.py`
- Test: `tests/unit/query/test_repository_coverage_data.py`

- [ ] **Step 1: Write failing repository summary/context/stats tests**

```python
def test_build_repository_context_returns_platforms_deployment_chain_and_limitations() -> None:
    result = build_repository_context(session, "api-node-boats")
    assert result["coverage"]["completeness_state"] == "complete"
    assert result["platforms"][0]["kind"] == "ecs"
    assert result["deploys_from"]
    assert result["provisioned_by"]
    assert result["iac_relationships"]
    assert result["summary"]
    assert result["deployment_chain"][0]["relationship_type"] in {
        "DEPLOYS_FROM",
        "DISCOVERS_CONFIG_IN",
        "RUNS_ON",
    }
    assert result["limitations"] == []


def test_build_repository_stats_surfaces_platform_and_deployment_counts() -> None:
    result = build_repository_stats(session, "api-node-boats")
    assert result["stats"]["platform_count"] >= 1
    assert result["stats"]["deployment_source_count"] >= 1
    assert "limitations" in result["stats"]
```

- [ ] **Step 2: Run the repository query tests to verify they fail**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/query/test_repository_runtime_context.py tests/unit/query/test_repository_coverage_data.py tests/unit/query/test_repository_queries.py -q`

Expected: FAIL because context/stats do not yet expose the new contracts.

- [ ] **Step 3: Implement a shared repository relationship summary layer**

```python
def build_relationship_summary(session: Any, repo_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "platforms": fetch_related_platforms(session, repo_ref),
        "deploys_from": fetch_deployment_sources(session, repo_ref),
        "discovers_config_in": fetch_config_repositories(session, repo_ref),
        "provisioned_by": fetch_provisioning_repositories(session, repo_ref),
        "provisions_dependencies_for": fetch_outbound_infra_relationships(session, repo_ref),
        "iac_relationships": fetch_iac_relationships(session, repo_ref),
        "deployment_chain": fetch_deployment_chain(session, repo_ref),
        "summary": build_repository_summary_fields(session, repo_ref),
        "environments": collect_environments(...),
        "limitations": build_limitations(...),
    }
```

- [ ] **Step 3a: Map every spec-required field to an assertion before implementation**

Create a checklist in the test file that covers:

```text
get_repo_summary:
- coverage
- platforms
- deploys_from
- discovers_config_in
- provisioned_by
- provisions_dependencies_for
- environments
- limitations

get_repository_stats:
- coverage
- platform_count
- deployment_source_count
- environment_count
- limitations

get_repository_context:
- summary
- coverage
- platforms
- deployment_chain
- iac_relationships
- environments
- limitations
```

- [ ] **Step 4: Run the repository query tests to verify they pass**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/query/test_repository_runtime_context.py tests/unit/query/test_repository_coverage_data.py tests/unit/query/test_repository_queries.py -q`

Expected: PASS

- [ ] **Step 5: Commit the repository query surface changes**

```bash
git add src/platform_context_graph/query/repositories/relationship_summary.py \
  src/platform_context_graph/query/repositories/context_data.py \
  src/platform_context_graph/query/repositories/stats_data.py \
  src/platform_context_graph/query/repositories/coverage_data.py \
  tests/unit/query/test_repository_runtime_context.py \
  tests/unit/query/test_repository_coverage_data.py \
  tests/unit/query/test_repository_queries.py
git commit -m "feat: surface runtime relationship summaries in repository queries"
```

### Task 6: Align MCP/API truthfulness, prompts, and observability

**Files:**
- Modify: `src/platform_context_graph/mcp/tools/handlers/ecosystem.py`
- Modify: `src/platform_context_graph/mcp/tools/ecosystem.py`
- Modify: `src/platform_context_graph/mcp/server.py`
- Modify: `src/platform_context_graph/api/routers/repositories.py`
- Modify: `src/platform_context_graph/prompts.py`
- Modify: `src/platform_context_graph/observability/structured_logging.py`
- Test: `tests/unit/handlers/test_repo_context.py`
- Test: `tests/integration/mcp/test_repository_runtime_context.py`
- Test: `tests/integration/api/test_repositories_api.py`

- [ ] **Step 1: Write failing MCP/API truthfulness tests**

```python
def test_get_repo_summary_reports_dns_unknown_when_entrypoint_evidence_is_missing() -> None:
    result = get_repo_summary(db_manager, "api-node-boats")
    assert "dns_unknown" in result["limitations"]


def test_repository_api_returns_platforms_and_limitations() -> None:
    response = client.get("/api/v0/repositories/repository:r_ab12cd34/context")
    assert response.json()["platforms"]
    assert "limitations" in response.json()
```

- [ ] **Step 2: Run the MCP/API tests to verify they fail**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/handlers/test_repo_context.py tests/integration/mcp/test_repository_runtime_context.py tests/integration/api/test_repositories_api.py -q`

Expected: FAIL because the handler contracts and prompts do not yet expose the widened payloads consistently.

- [ ] **Step 3: Implement contract alignment and tracing/logging**

Add structured handler behavior like:

```python
emit_log_call(
    warning_logger,
    "Repository runtime context assembled with known limitations",
    event_name="repository.context.limitations",
    extra_keys={
        "repo_id": repo_id,
        "limitations": limitations,
        "platform_count": len(platforms),
    },
)
```

and add OTEL span attributes for limitation counts, platform counts, and deployment-chain completeness.

- [ ] **Step 4: Run the MCP/API tests to verify they pass**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/handlers/test_repo_context.py tests/integration/mcp/test_repository_runtime_context.py tests/integration/api/test_repositories_api.py -q`

Expected: PASS

- [ ] **Step 5: Commit the MCP/API truthfulness changes**

```bash
git add src/platform_context_graph/mcp/tools/handlers/ecosystem.py \
  src/platform_context_graph/mcp/tools/ecosystem.py \
  src/platform_context_graph/mcp/server.py \
  src/platform_context_graph/api/routers/repositories.py \
  src/platform_context_graph/prompts.py \
  src/platform_context_graph/observability/structured_logging.py \
  tests/unit/handlers/test_repo_context.py \
  tests/integration/mcp/test_repository_runtime_context.py \
  tests/integration/api/test_repositories_api.py
git commit -m "feat: expose canonical runtime context through MCP and API"
```

### Task 7: Lock acceptance fixtures and compose/runtime verification

**Files:**
- Create: `tests/fixtures/ecosystems/platform_runtime_corpus/`
- Modify: `docker-compose.yaml`
- Modify: `docker-compose.template.yml`
- Modify: `docs/docs/reference/relationship-mapping.md`
- Modify: `src/platform_context_graph/relationships/README.md`
- Test: `tests/integration/runtime/test_compose_env_contract.py`
- Test: `tests/integration/test_full_flow.py`
- Test: `tests/integration/mcp/test_repository_runtime_context.py`

- [ ] **Step 1: Add failing acceptance coverage for ECS/EKS/runtime chains**

```python
def test_platform_runtime_corpus_surfaces_ecs_and_eks_chains(indexed_yaml) -> None:
    summary = get_repo_summary(indexed_yaml, "api-node-boats")
    assert any(item["kind"] == "ecs" for item in summary["platforms"])
    assert any(
        edge["relationship_type"] == "PROVISIONS_PLATFORM"
        for edge in summary["iac_relationships"]
    )
```

- [ ] **Step 2: Run the acceptance-focused tests to verify they fail**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/integration/test_full_flow.py tests/integration/mcp/test_repository_runtime_context.py -q`

Expected: FAIL because the fixture corpus and acceptance assertions do not yet exist.

- [ ] **Step 3: Add portable fixtures and an automated compose env contract**

Document the fixture corpus around:

```text
platform_runtime_corpus/
  terraform-stack-ecs/
  terraform-stack-external-search/
  iac-eks-argocd/
  iac-eks-observability/
  helm-charts/
  api-node-boats/
```

and ensure compose files preserve:

```yaml
PCG_PARSE_WORKERS: "${PCG_PARSE_WORKERS:-4}"
PCG_INDEX_QUEUE_DEPTH: "${PCG_INDEX_QUEUE_DEPTH:-8}"
```

Add a concrete automated test in `tests/integration/runtime/test_compose_env_contract.py`:

```python
def test_compose_services_define_parse_workers_and_queue_depth() -> None:
    config = yaml.safe_load(Path("docker-compose.yaml").read_text())
    for service_name in ("bootstrap-index", "platform-context-graph", "repo-sync"):
        environment = config["services"][service_name]["environment"]
        assert environment["PCG_PARSE_WORKERS"] == "${PCG_PARSE_WORKERS:-4}"
        assert environment["PCG_INDEX_QUEUE_DEPTH"] == "${PCG_INDEX_QUEUE_DEPTH:-8}"
```

- [ ] **Step 4: Run the acceptance-focused tests to verify they pass**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/integration/runtime/test_compose_env_contract.py tests/integration/test_full_flow.py tests/integration/mcp/test_repository_runtime_context.py -q`

Expected: PASS

- [ ] **Step 5: Commit the acceptance corpus and docs**

```bash
git add tests/fixtures/ecosystems/platform_runtime_corpus \
  docker-compose.yaml \
  docker-compose.template.yml \
  docs/docs/reference/relationship-mapping.md \
  src/platform_context_graph/relationships/README.md \
  tests/integration/runtime/test_compose_env_contract.py \
  tests/integration/test_full_flow.py \
  tests/integration/mcp/test_repository_runtime_context.py
git commit -m "test: add canonical platform acceptance coverage"
```

### Task 8: Run the full verification matrix and capture acceptance evidence

**Files:**
- Modify: `docs/superpowers/plans/2026-03-26-canonical-platform-entities-implementation.md`
- Test: `tests/unit`
- Test: `tests/integration`
- Test: `tests/e2e`

- [ ] **Step 1: Run focused local verification after the last code change**

Run:

```bash
PYTHONPATH=src uv run --extra dev python -m pytest \
  tests/unit/relationships/test_entities.py \
  tests/unit/relationships/test_platform_resolution.py \
  tests/unit/relationships/test_file_evidence.py \
  tests/unit/query/test_repository_runtime_context.py \
  tests/unit/handlers/test_repo_context.py -q
```

Expected: PASS

- [ ] **Step 2: Run the full repository verification matrix**

Run:

```bash
uv run python scripts/check_python_file_lengths.py
uv run python scripts/check_python_docstrings.py
PYTHONPATH=src uv run --extra dev python -m pytest tests/unit -q
PYTHONPATH=src uv run --extra dev python -m pytest tests/integration -q
PYTHONPATH=src uv run --extra dev python -m pytest tests/e2e -q
uvx --with mkdocs-material mkdocs build -f docs/mkdocs.yml
```

Expected:

- file length check passes
- docstring check passes
- unit tests pass
- integration tests pass
- e2e tests pass
- docs build passes with no new warnings introduced by this slice

- [ ] **Step 3: Run Docker Compose acceptance verification on the portable corpus**

Run:

```bash
docker compose -p pcg-platform-runtime down -v
PCG_FILESYSTEM_HOST_ROOT=/Users/allen/.pcg-test-corpora/testing-1 \
PCG_LOG_FORMAT=json \
docker compose -p pcg-platform-runtime up --build bootstrap-index
```

Then verify:

```bash
docker compose -p pcg-platform-runtime exec postgres psql \
  postgresql://pcg:testpassword@postgres:5432/platform_context_graph \
  -c "select relationship_type, count(*) from resolved_relationships group by 1 order by 1;"
```

Expected:

- bootstrap completes successfully
- JSON logs include relationship entity and limitation events
- typed edges include `RUNS_ON`, `PROVISIONS_PLATFORM`, `DEPLOYS_FROM`, and `DISCOVERS_CONFIG_IN`
- no false canonical platform created with `platform:*:*:none:none:none`

- [ ] **Step 4: Update this plan with actual verification outputs**

Add a short execution note under each completed task with the command result summary and any deviations from expected output.

- [ ] **Step 5: Commit the final verification evidence**

```bash
git add docs/superpowers/plans/2026-03-26-canonical-platform-entities-implementation.md
git commit -m "docs: record canonical platform implementation verification"
```
