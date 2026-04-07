# PCG Investigation Orchestration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class `investigate_service` orchestration flow that widens across deployment-adjacent repositories, reports coverage explicitly, detects multi-plane deployment evidence, and exposes the result through MCP and HTTP without requiring prompt-expert users to manually guide repo expansion.

**Architecture:** Introduce a dedicated investigation contract and query-layer orchestrator rather than hiding more logic inside existing story endpoints. The new orchestrator will reuse current resolution, story, trace, repo-context, and content-query primitives, then add explicit evidence-family widening, coverage accounting, multi-plane detection, and next-step recommendations. Existing story surfaces will receive lightweight investigation hints, but the new top-level tool remains the primary operator-facing entrypoint.

**Tech Stack:** Python, FastAPI, Pydantic, existing PCG query modules, MCP tool manifests, pytest

---

## File Structure

### New files

- `src/platform_context_graph/domain/investigation_responses.py`
  Purpose: Pydantic response models for investigation results and reusable coverage/evidence-family structures.
- `src/platform_context_graph/query/investigation.py`
  Purpose: public query-service entrypoint for service investigations.
- `src/platform_context_graph/query/investigation_service.py`
  Purpose: main `investigate_service(...)` orchestration flow.
- `src/platform_context_graph/query/investigation_intent.py`
  Purpose: intent normalization and question-family helpers.
- `src/platform_context_graph/query/investigation_evidence_families.py`
  Purpose: evidence-family constants and family-specific accumulation helpers.
- `src/platform_context_graph/query/investigation_repo_widening.py`
  Purpose: related-repository widening logic and justification metadata.
- `src/platform_context_graph/query/investigation_coverage.py`
  Purpose: coverage summaries, limitations, and sparse vs multi-plane classification.
- `src/platform_context_graph/query/investigation_recommendations.py`
  Purpose: recommended next steps and next-call generation.
- `src/platform_context_graph/mcp/tools/handlers/investigation.py`
  Purpose: MCP handler for `investigate_service`.
- `src/platform_context_graph/api/routers/investigations.py`
  Purpose: HTTP route for the investigation endpoint.
- `tests/unit/query/test_investigation_intent.py`
  Purpose: TDD for intent inference and normalization.
- `tests/unit/query/test_investigation_repo_widening.py`
  Purpose: TDD for related-repo widening and justification logic.
- `tests/unit/query/test_investigation_service.py`
  Purpose: TDD for orchestration flow, multi-plane detection, and coverage reporting.
- `tests/unit/mcp/test_investigation_handler.py`
  Purpose: MCP contract tests for the new tool.
- `tests/integration/api/test_investigation_api.py`
  Purpose: HTTP route and response-model contract tests.

### Existing files to modify

- `src/platform_context_graph/domain/responses.py`
  Purpose: export or reference the new investigation response model without overloading the existing story model file.
- `src/platform_context_graph/query/__init__.py`
  Purpose: add the new `investigation` query module to the query-service bundle.
- `src/platform_context_graph/api/dependencies.py`
  Purpose: wire `investigation` into `QueryServices`.
- `src/platform_context_graph/api/app.py`
  Purpose: include the new router.
- `src/platform_context_graph/api/app_openapi.py`
  Purpose: register OpenAPI examples for the new route.
- `src/platform_context_graph/api/app_openapi_examples.py`
  Purpose: add stable investigation examples.
- `src/platform_context_graph/mcp/tools/context.py`
  Purpose: add the `investigate_service` MCP tool definition.
- `src/platform_context_graph/mcp/tools/handlers/__init__.py`
  Purpose: export the new handler if needed by the MCP loader.
- `src/platform_context_graph/query/story_workload_support.py`
  Purpose: surface investigation hints on service story responses without duplicating orchestration.
- `src/platform_context_graph/query/story_repository_support.py`
  Purpose: optionally expose related-repo / evidence-family hints to repository stories.
- `tests/integration/api/test_openapi_contract.py`
  Purpose: assert the new HTTP schema and examples.
- `tests/unit/handlers/test_repo_context_story_overviews.py`
  Purpose: add lightweight regression coverage for investigation hints if story surfaces are updated.
- `docs/docs/reference/http-api.md`
  Purpose: document the new investigation endpoint.
- `docs/docs/reference/mcp-reference.md`
  Purpose: document the new MCP tool contract.
- `docs/docs/use-cases.md`
  Purpose: add operator-oriented examples showing short prompts.

---

## Chunk 1: Contract And Intent

### Task 1: Add the investigation response contract

**Files:**
- Create: `src/platform_context_graph/domain/investigation_responses.py`
- Modify: `src/platform_context_graph/domain/responses.py`
- Test: `tests/integration/api/test_openapi_contract.py`

- [ ] **Step 1: Write the failing response-model contract test**

Add a new test near the existing OpenAPI contract assertions that expects a
typed `InvestigationResponse` schema to exist once the endpoint is added.

```python
def test_openapi_uses_typed_response_model_for_investigation_route() -> None:
    with _make_client(query_services=_make_query_services()) as client:
        schema = client.get("/api/v0/openapi.json").json()

    investigation_schema = schema["paths"]["/api/v0/investigations/services/{service_name}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert investigation_schema["$ref"] == "#/components/schemas/InvestigationResponse"
```

- [ ] **Step 2: Run the contract test to confirm it fails**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/integration/api/test_openapi_contract.py -k investigation -v`
Expected: FAIL because the route and schema do not exist yet.

- [ ] **Step 3: Add the minimal investigation response models**

Create focused Pydantic models for:

- `InvestigationFinding`
- `InvestigationCoverageSummary`
- `InvestigationRepositoryEvidence`
- `InvestigationNextCall`
- `InvestigationResponse`

Keep this file standalone so `responses.py` does not continue to grow.

```python
class InvestigationResponse(BaseModel):
    summary: list[str] = Field(default_factory=list)
    repositories_considered: list[InvestigationRepositoryEvidence] = Field(default_factory=list)
    repositories_with_evidence: list[InvestigationRepositoryEvidence] = Field(default_factory=list)
    evidence_families_found: list[str] = Field(default_factory=list)
    coverage_summary: InvestigationCoverageSummary
    investigation_findings: list[InvestigationFinding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    recommended_next_calls: list[InvestigationNextCall] = Field(default_factory=list)
```

- [ ] **Step 4: Export the model in the shared response surface**

Update `src/platform_context_graph/domain/responses.py` to import and expose
the investigation model without duplicating field definitions.

- [ ] **Step 5: Re-run the contract test**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/integration/api/test_openapi_contract.py -k investigation -v`
Expected: still FAIL because the route is not wired yet, but schema imports should be valid.

- [ ] **Step 6: Commit**

```bash
git add src/platform_context_graph/domain/investigation_responses.py src/platform_context_graph/domain/responses.py tests/integration/api/test_openapi_contract.py
git commit -m "feat: add investigation response contract"
```

### Task 2: Add intent inference and evidence-family primitives

**Files:**
- Create: `src/platform_context_graph/query/investigation_intent.py`
- Create: `src/platform_context_graph/query/investigation_evidence_families.py`
- Test: `tests/unit/query/test_investigation_intent.py`

- [ ] **Step 1: Write the failing intent test**

Add parameterized tests for deployment, network, dependency, support, and
overview classification.

```python
@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Explain the deployment flow for api-node-boats", "deployment"),
        ("What depends on api-node-boats", "dependencies"),
        ("Explain the network flow for api-node-boats", "network"),
    ],
)
def test_infer_investigation_intent(question: str, expected: str) -> None:
    assert infer_investigation_intent(question) == expected
```

- [ ] **Step 2: Run the new test to confirm it fails**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/query/test_investigation_intent.py -v`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the minimal intent and evidence-family helpers**

Create:

- `infer_investigation_intent(...)`
- `normalize_investigation_intent(...)`
- evidence-family constants such as:
  - `service_runtime`
  - `deployment_controller`
  - `gitops_config`
  - `iac_infrastructure`
  - `network_routing`
  - `identity_and_iam`
  - `dependencies`
  - `support_artifacts`
  - `monitoring_observability`
  - `ci_cd_pipeline`

- [ ] **Step 4: Re-run the intent tests**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/query/test_investigation_intent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/query/investigation_intent.py src/platform_context_graph/query/investigation_evidence_families.py tests/unit/query/test_investigation_intent.py
git commit -m "feat: add investigation intent helpers"
```

## Chunk 2: Repo Widening And Coverage

### Task 3: Add factual related-repo widening

**Files:**
- Create: `src/platform_context_graph/query/investigation_repo_widening.py`
- Test: `tests/unit/query/test_investigation_repo_widening.py`

- [ ] **Step 1: Write the failing widening tests**

Cover at least these cases:

- AppSet source repo causes widening into the deploy repo
- Terraform OIDC / role-subject evidence causes widening into a Terraform repo
- App repo `.github/` workflow evidence causes widening into deploy or release repos
- Widening result includes a reason, not just a repo id

```python
def test_widening_adds_repo_when_appset_references_external_source_repo() -> None:
    candidates = widen_related_repositories(
        service_name="api-node-boats",
        primary_repo="api-node-boats",
        deployment_trace={
            "argocd_applicationsets": [
                {"source_repos": ["https://github.com/boatsgroup/helm-charts"]}
            ]
        },
    )
    assert any(item["repo_name"] == "helm-charts" for item in candidates)
```

- [ ] **Step 2: Run the widening tests to confirm they fail**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/query/test_investigation_repo_widening.py -v`
Expected: FAIL because the widening module does not exist.

- [ ] **Step 3: Implement the minimal widening helper**

Build one focused helper that accepts already-fetched evidence fragments and
returns:

- candidate repo id or repo name
- evidence family
- reason
- confidence band

Keep the function pure and testable; do not fetch from the database inside it.

- [ ] **Step 4: Re-run the widening tests**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/query/test_investigation_repo_widening.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/query/investigation_repo_widening.py tests/unit/query/test_investigation_repo_widening.py
git commit -m "feat: add investigation repo widening"
```

### Task 4: Add coverage and multi-plane reporting helpers

**Files:**
- Create: `src/platform_context_graph/query/investigation_coverage.py`
- Test: `tests/unit/query/test_investigation_service.py`

- [ ] **Step 1: Write the failing coverage tests**

Add tests for:

- `single_plane`
- `multi_plane`
- `sparse`

and for the distinction between:

- searched but no evidence
- evidence found but partial
- not searched

```python
def test_build_coverage_summary_marks_multi_plane_when_controller_and_iac_exist() -> None:
    summary = build_investigation_coverage_summary(
        evidence_families_found=["deployment_controller", "iac_infrastructure"],
        searched_families=["deployment_controller", "iac_infrastructure", "network_routing"],
        deployment_planes=["gitops_kubernetes", "terraform_ecs"],
    )
    assert summary.deployment_mode == "multi_plane"
```

- [ ] **Step 2: Run the targeted tests to confirm they fail**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/query/test_investigation_service.py -k coverage -v`
Expected: FAIL

- [ ] **Step 3: Implement the minimal coverage helper**

Return a small structured summary with:

- searched families
- found families
- missing families
- deployment mode
- graph/content caveats

- [ ] **Step 4: Re-run the coverage tests**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/query/test_investigation_service.py -k coverage -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/query/investigation_coverage.py tests/unit/query/test_investigation_service.py
git commit -m "feat: add investigation coverage summaries"
```

## Chunk 3: Service Orchestrator

### Task 5: Implement `investigate_service(...)` in the query layer

**Files:**
- Create: `src/platform_context_graph/query/investigation_service.py`
- Create: `src/platform_context_graph/query/investigation_recommendations.py`
- Create: `src/platform_context_graph/query/investigation.py`
- Modify: `src/platform_context_graph/query/__init__.py`
- Modify: `src/platform_context_graph/api/dependencies.py`
- Test: `tests/unit/query/test_investigation_service.py`

- [ ] **Step 1: Write the failing orchestration tests**

Cover these scenarios:

- service investigation widens from app repo into Helm/GitOps repo
- service investigation widens into Terraform stack when IAM/OIDC evidence exists
- multi-plane result keeps GitOps/Kubernetes and Terraform/ECS separate
- app repo `.github/` evidence becomes `ci_cd_pipeline`
- result contains recommended next calls when coverage is partial

```python
def test_investigate_service_surfaces_dual_deployment_planes() -> None:
    result = investigate_service(
        database=fake_database,
        service_name="api-node-boats",
        intent="deployment",
    )
    assert result["coverage_summary"]["deployment_mode"] == "multi_plane"
    assert {plane["name"] for plane in result["coverage_summary"]["deployment_planes"]} == {
        "gitops_kubernetes",
        "terraform_ecs",
    }
```

- [ ] **Step 2: Run the orchestration tests to confirm they fail**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/query/test_investigation_service.py -v`
Expected: FAIL because the query module does not exist.

- [ ] **Step 3: Implement the minimal orchestrator**

`investigate_service(...)` should:

1. resolve the service and primary repo
2. pull base evidence from existing queries:
   - `resolve_entity`
   - `get_service_story`
   - `trace_deployment_chain`
   - `get_repo_story`
   - `get_repo_context`
   - targeted `search_file_content`
3. widen into related repos using the pure widening helper
4. aggregate evidence families
5. build coverage summary
6. build recommended next steps and next calls

Keep fetching/orchestration in `investigation_service.py` and keep pure shaping
logic in helper modules.

- [ ] **Step 4: Wire the query module into the shared service bundle**

Update:

- `src/platform_context_graph/query/investigation.py`
- `src/platform_context_graph/query/__init__.py`
- `src/platform_context_graph/api/dependencies.py`

so `services.investigation.investigate_service(...)` is available to HTTP and
MCP surfaces.

- [ ] **Step 5: Re-run the orchestration tests**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/query/test_investigation_service.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/platform_context_graph/query/investigation.py src/platform_context_graph/query/investigation_service.py src/platform_context_graph/query/investigation_recommendations.py src/platform_context_graph/query/__init__.py src/platform_context_graph/api/dependencies.py tests/unit/query/test_investigation_service.py
git commit -m "feat: add service investigation orchestrator"
```

## Chunk 4: MCP And HTTP Exposure

### Task 6: Add the MCP tool definition and handler

**Files:**
- Modify: `src/platform_context_graph/mcp/tools/context.py`
- Create: `src/platform_context_graph/mcp/tools/handlers/investigation.py`
- Modify: `src/platform_context_graph/mcp/tools/handlers/__init__.py`
- Test: `tests/unit/mcp/test_investigation_handler.py`

- [ ] **Step 1: Write the failing MCP handler tests**

Assert:

- the handler delegates to `services.investigation.investigate_service`
- the result is returned unchanged on success
- errors are surfaced using the current handler style

```python
def test_investigate_service_handler_delegates_to_query_service() -> None:
    result = investigation.investigate_service(
        services=services,
        service_name="api-node-boats",
        intent="deployment",
    )
    assert result["summary"] == ["dual deployment detected"]
```

- [ ] **Step 2: Run the MCP tests to confirm they fail**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/mcp/test_investigation_handler.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the MCP tool**

Add `investigate_service` to `CONTEXT_TOOLS` with:

- `service_name`
- optional `environment`
- optional `intent`
- optional `question`

and wire the handler module.

- [ ] **Step 4: Re-run the MCP tests**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/mcp/test_investigation_handler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/mcp/tools/context.py src/platform_context_graph/mcp/tools/handlers/investigation.py src/platform_context_graph/mcp/tools/handlers/__init__.py tests/unit/mcp/test_investigation_handler.py
git commit -m "feat: expose service investigation over MCP"
```

### Task 7: Add the HTTP endpoint and OpenAPI examples

**Files:**
- Create: `src/platform_context_graph/api/routers/investigations.py`
- Modify: `src/platform_context_graph/api/app.py`
- Modify: `src/platform_context_graph/api/app_openapi.py`
- Modify: `src/platform_context_graph/api/app_openapi_examples.py`
- Test: `tests/integration/api/test_investigation_api.py`
- Test: `tests/integration/api/test_openapi_contract.py`

- [ ] **Step 1: Write the failing HTTP tests**

Cover:

- route returns typed `InvestigationResponse`
- optional `environment` and `intent` are forwarded
- OpenAPI includes a stable example

```python
def test_investigation_route_uses_investigation_query_service() -> None:
    with _make_client(query_services=_make_query_services()) as client:
        response = client.get(
            "/api/v0/investigations/services/api-node-boats?intent=deployment"
        )
    assert response.status_code == 200
    assert response.json()["coverage_summary"]["deployment_mode"] == "multi_plane"
```

- [ ] **Step 2: Run the HTTP tests to confirm they fail**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/integration/api/test_investigation_api.py tests/integration/api/test_openapi_contract.py -k investigation -v`
Expected: FAIL

- [ ] **Step 3: Implement the HTTP route and OpenAPI example**

Add a new router under `/api/v0/investigations/services/{service_name}` and
register it in `app.py`. Add a stable example to the OpenAPI helpers.

- [ ] **Step 4: Re-run the HTTP and OpenAPI tests**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/integration/api/test_investigation_api.py tests/integration/api/test_openapi_contract.py -k investigation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/api/routers/investigations.py src/platform_context_graph/api/app.py src/platform_context_graph/api/app_openapi.py src/platform_context_graph/api/app_openapi_examples.py tests/integration/api/test_investigation_api.py tests/integration/api/test_openapi_contract.py
git commit -m "feat: add investigation HTTP endpoint"
```

## Chunk 5: Story Hints, Docs, And Acceptance

### Task 8: Add investigation hints to existing story surfaces

**Files:**
- Modify: `src/platform_context_graph/query/story_workload_support.py`
- Modify: `src/platform_context_graph/query/story_repository_support.py`
- Test: `tests/unit/query/test_story_workload_support.py`
- Test: `tests/unit/handlers/test_repo_context_story_overviews.py`

- [ ] **Step 1: Write the failing story-hint tests**

Add coverage that story surfaces can expose lightweight investigation hints
without embedding the full orchestration payload.

```python
def test_service_story_exposes_related_repo_hints_for_investigation() -> None:
    response = build_workload_story_response(...)
    assert "investigation_hints" in response["drilldowns"]
```

- [ ] **Step 2: Run the targeted tests to confirm they fail**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/query/test_story_workload_support.py tests/unit/handlers/test_repo_context_story_overviews.py -k investigation -v`
Expected: FAIL

- [ ] **Step 3: Implement minimal hints**

Expose only:

- likely related repos
- likely evidence families
- suggested next drill-down

Do not duplicate full `investigate_service` output in story responses.

- [ ] **Step 4: Re-run the targeted tests**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/unit/query/test_story_workload_support.py tests/unit/handlers/test_repo_context_story_overviews.py -k investigation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/query/story_workload_support.py src/platform_context_graph/query/story_repository_support.py tests/unit/query/test_story_workload_support.py tests/unit/handlers/test_repo_context_story_overviews.py
git commit -m "feat: add investigation hints to story surfaces"
```

### Task 9: Document the new investigation flow and validate end-to-end

**Files:**
- Modify: `docs/docs/reference/http-api.md`
- Modify: `docs/docs/reference/mcp-reference.md`
- Modify: `docs/docs/use-cases.md`
- Test: `tests/integration/api/test_story_api.py`
- Test: `tests/integration/api/test_investigation_api.py`

- [ ] **Step 1: Write or extend the acceptance tests**

Add one acceptance-style test proving a short support prompt shape can receive
the investigation contract with:

- related repos
- evidence families
- coverage summary
- recommended next calls

```python
def test_investigation_response_exposes_operator_coverage_fields() -> None:
    response = client.get("/api/v0/investigations/services/api-node-boats")
    payload = response.json()
    assert "repositories_considered" in payload
    assert "evidence_families_found" in payload
    assert "recommended_next_calls" in payload
```

- [ ] **Step 2: Run the focused integration tests**

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/integration/api/test_investigation_api.py tests/integration/api/test_story_api.py -k investigation -v`
Expected: PASS after the endpoint and hints are complete.

- [ ] **Step 3: Update the docs**

Document:

- when to use `investigate_service`
- how coverage reporting works
- what evidence families mean
- how recommended-next-call guidance should be interpreted

- [ ] **Step 4: Build docs and re-run the integration tests**

Run: `uv run --with mkdocs-material mkdocs build --strict`
Expected: PASS

Run: `PYTHONPATH=src:. uv run --with pytest python -m pytest tests/integration/api/test_investigation_api.py tests/integration/api/test_story_api.py -k investigation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/docs/reference/http-api.md docs/docs/reference/mcp-reference.md docs/docs/use-cases.md tests/integration/api/test_investigation_api.py tests/integration/api/test_story_api.py
git commit -m "docs: document service investigation flow"
```

## Final Verification

- [ ] **Step 1: Run the focused unit and integration suite**

Run:

```bash
PYTHONPATH=src:. uv run --with pytest python -m pytest \
  tests/unit/query/test_investigation_intent.py \
  tests/unit/query/test_investigation_repo_widening.py \
  tests/unit/query/test_investigation_service.py \
  tests/unit/mcp/test_investigation_handler.py \
  tests/integration/api/test_investigation_api.py \
  tests/integration/api/test_openapi_contract.py \
  tests/integration/api/test_story_api.py -v
```

Expected: PASS

- [ ] **Step 2: Run format, compile, and guardrail checks**

Run:

```bash
uv run --with black black --check src/platform_context_graph/domain/investigation_responses.py src/platform_context_graph/query/investigation.py src/platform_context_graph/query/investigation_service.py src/platform_context_graph/query/investigation_intent.py src/platform_context_graph/query/investigation_evidence_families.py src/platform_context_graph/query/investigation_repo_widening.py src/platform_context_graph/query/investigation_coverage.py src/platform_context_graph/query/investigation_recommendations.py src/platform_context_graph/mcp/tools/handlers/investigation.py src/platform_context_graph/api/routers/investigations.py
python3 scripts/check_python_file_lengths.py
python3 scripts/check_python_docstrings.py
python3 -m py_compile src/platform_context_graph/domain/investigation_responses.py src/platform_context_graph/query/investigation.py src/platform_context_graph/query/investigation_service.py src/platform_context_graph/query/investigation_intent.py src/platform_context_graph/query/investigation_evidence_families.py src/platform_context_graph/query/investigation_repo_widening.py src/platform_context_graph/query/investigation_coverage.py src/platform_context_graph/query/investigation_recommendations.py src/platform_context_graph/mcp/tools/handlers/investigation.py src/platform_context_graph/api/routers/investigations.py
git diff --check
```

Expected: PASS

- [ ] **Step 3: Push and open a draft PR**

```bash
gh auth switch --user linuxdynasty
git push -u origin codex/pcg-investigation-orchestration
gh pr create --draft --title "feat: add PCG investigation orchestration" --body-file <prepared-body>
```

Expected: branch pushed and draft PR opened from the worktree branch.

## Notes For Execution

- Keep every new Python file under 500 lines. Split helpers early instead of
  waiting for CI to fail.
- Prefer pure helper modules for classification, widening, coverage, and
  recommendation logic so unit tests stay fast.
- Reuse existing query modules rather than reimplementing resolution, story, or
  content search logic.
- Do not let the new orchestrator silently swallow partial coverage. Limitations
  are a feature here, not noise.
- Treat app repo `.github/` workflow evidence as a first-class CI/CD source in
  both widening and findings.
