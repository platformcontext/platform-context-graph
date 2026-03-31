# API Node Boats Local E2E Reindex Harness Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only, compose-backed, full end-to-end harness that bootstraps and scan-reindexes the `api-node-boats` ecosystem from disposable clones and validates the promoted PCG repository story and context contracts.

**Architecture:** Add a generic Python harness that reads a user-supplied local manifest, ensures the required repos exist under `~/repos`, mirrors them into disposable bare remotes, creates disposable working copies, and drives the existing compose stack against that isolated corpus. Reuse the public HTTP API for entity resolution plus repository story/context validation, and add a scan phase that makes evidence-bearing upstream commits in the disposable remotes before calling the real scan API.

**Tech Stack:** Python, pytest, FastAPI HTTP API, docker compose, Neo4j, Postgres, git bare remotes, shell wrapper scripts.

---

## Chunk 1: Manifest and Workspace Plumbing

### Task 1: Add failing tests for local manifest parsing and validation

**Files:**
- Create: `tests/unit/scripts/test_api_node_boats_e2e_manifest.py`
- Reference: `scripts/seed_e2e_graph.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_load_manifest_parses_required_and_optional_repositories(tmp_path: Path) -> None:
    ...

def test_load_manifest_requires_bootstrap_and_scan_assertions(tmp_path: Path) -> None:
    ...

def test_load_manifest_requires_scan_mutation_targets(tmp_path: Path) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_manifest.py -q`
Expected: FAIL because the manifest loader module does not exist yet.

- [ ] **Step 3: Write minimal implementation**

**Files:**
- Create: `scripts/api_node_boats_e2e_manifest.py`

Implement typed manifest loading with:
- explicit schema validation for:
  - repo list
  - required vs optional flags
  - clone roots
  - bootstrap assertions
  - scan mutations
  - scan assertions
- path-expansion for local manifest file locations
- helpful error messages for incomplete local-only manifest files

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_manifest.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/scripts/test_api_node_boats_e2e_manifest.py scripts/api_node_boats_e2e_manifest.py
git commit -m "feat: add local api-node-boats e2e manifest loader"
```

### Task 2: Add failing tests for disposable repo workspace planning

**Files:**
- Create: `tests/unit/scripts/test_api_node_boats_e2e_workspace.py`
- Test: `scripts/api_node_boats_e2e_workspace.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_plan_workspace_groups_repositories_by_clone_root(tmp_path: Path) -> None:
    ...

def test_plan_workspace_reports_missing_required_repositories() -> None:
    ...

def test_plan_workspace_leaves_optional_missing_repositories_as_diagnostics() -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_workspace.py -q`
Expected: FAIL because the workspace planner does not exist yet.

- [ ] **Step 3: Write minimal implementation**

**Files:**
- Create: `scripts/api_node_boats_e2e_workspace.py`

Implement:
- repo resolution from local roots:
  - `~/repos/services`
  - `~/repos/terraform-stacks`
  - `~/repos/terraform-modules`
  - `~/repos/mobius`
  - `~/repos/libs`
  - `~/repos/ansible-automate`
- detection of missing required and optional repos
- expansion of target clone paths for missing repos
- a focused plan object that the runtime harness can execute

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_workspace.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/scripts/test_api_node_boats_e2e_workspace.py scripts/api_node_boats_e2e_workspace.py
git commit -m "feat: add api-node-boats e2e workspace planner"
```

## Chunk 2: Disposable Remotes and Bootstrap Flow

### Task 3: Add failing tests for disposable bare remotes and working copies

**Files:**
- Create: `tests/unit/scripts/test_api_node_boats_e2e_git_runtime.py`
- Test: `scripts/api_node_boats_e2e_git_runtime.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_create_bare_remote_from_local_repository(tmp_path: Path) -> None:
    ...

def test_create_disposable_working_copy_tracks_bare_remote(tmp_path: Path) -> None:
    ...

def test_disposable_working_copy_can_commit_and_push(tmp_path: Path) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_git_runtime.py -q`
Expected: FAIL because the git runtime helper does not exist yet.

- [ ] **Step 3: Write minimal implementation**

**Files:**
- Create: `scripts/api_node_boats_e2e_git_runtime.py`

Implement:
- copy or clone local repos into disposable bare remotes
- clone disposable working copies from those remotes
- set deterministic author metadata for synthetic commits
- helper to push evidence-bearing changes into the fake upstream

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_git_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/scripts/test_api_node_boats_e2e_git_runtime.py scripts/api_node_boats_e2e_git_runtime.py
git commit -m "feat: add disposable git runtime for api-node-boats e2e"
```

### Task 4: Add failing tests for local auto-clone orchestration

**Files:**
- Create: `tests/unit/scripts/test_api_node_boats_e2e_clone_support.py`
- Test: `scripts/api_node_boats_e2e_clone_support.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_clone_support_skips_existing_repositories(tmp_path: Path) -> None:
    ...

def test_clone_support_clones_missing_required_repository(tmp_path: Path, mocker) -> None:
    ...

def test_clone_support_surfaces_failed_required_clone() -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_clone_support.py -q`
Expected: FAIL because the clone helper does not exist yet.

- [ ] **Step 3: Write minimal implementation**

**Files:**
- Create: `scripts/api_node_boats_e2e_clone_support.py`

Implement:
- local repo presence checks
- missing-repo clone support via `gh repo clone` or `git clone`
- no-op behavior for already-present repos
- clear separation between:
  - required repo clone failures
  - optional repo clone failures

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_clone_support.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/scripts/test_api_node_boats_e2e_clone_support.py scripts/api_node_boats_e2e_clone_support.py
git commit -m "feat: add auto-clone support for api-node-boats e2e harness"
```

## Chunk 3: HTTP Contract Validation and Scan Assertions

### Task 5: Add failing tests for HTTP contract checks

**Files:**
- Create: `tests/unit/scripts/test_api_node_boats_e2e_http_contract.py`
- Test: `scripts/api_node_boats_e2e_http_contract.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_resolve_repository_by_plain_name_uses_entities_resolve() -> None:
    ...

def test_validate_bootstrap_contract_requires_story_and_context_fields() -> None:
    ...

def test_validate_scan_contract_requires_repo_reprocessing_and_story_delta() -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_http_contract.py -q`
Expected: FAIL because the HTTP contract helper does not exist yet.

- [ ] **Step 3: Write minimal implementation**

**Files:**
- Create: `scripts/api_node_boats_e2e_http_contract.py`

Implement:
- exact repo resolution via `POST /api/v0/entities/resolve`
- canonical-id story fetch via `GET /api/v0/repositories/{id}/story`
- canonical-id context fetch via `GET /api/v0/repositories/{id}/context`
- validation helpers for the agreed blocking contract:
  - story non-empty
  - `v3`
  - `/_specs`
  - hostnames
  - `terraform-stack-node10`
  - ECS platform
  - `helm-charts`
  - environment presence
  - upstream dependency on `api-node-forex`
- scan validation helpers for:
  - mutated repo reprocessing evidence
  - measurable `api-node-boats` downstream delta

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_http_contract.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/scripts/test_api_node_boats_e2e_http_contract.py scripts/api_node_boats_e2e_http_contract.py
git commit -m "feat: add api-node-boats e2e http contract checks"
```

### Task 6: Add failing tests for evidence-bearing mutation helpers

**Files:**
- Create: `tests/unit/scripts/test_api_node_boats_e2e_mutations.py`
- Test: `scripts/api_node_boats_e2e_mutations.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_apply_workflow_mutation_updates_manual_deploy_workflow(tmp_path: Path) -> None:
    ...

def test_apply_terraform_mutation_updates_api_node_boats_ecs_block(tmp_path: Path) -> None:
    ...

def test_mutations_are_idempotent_for_repeat_runs(tmp_path: Path) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_mutations.py -q`
Expected: FAIL because the mutation helper does not exist yet.

- [ ] **Step 3: Write minimal implementation**

**Files:**
- Create: `scripts/api_node_boats_e2e_mutations.py`

Implement safe, parseable mutations for:
- `api-node-provisioning-indexer/.github/workflows/manual-deploy.yml`
- `terraform-stack-node10/shared/ecs.tf`

Constraints:
- no comment-only markers
- add or update structured keys or values that the existing extractors can observe
- keep mutations deterministic and reversible

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/unit/scripts/test_api_node_boats_e2e_mutations.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/scripts/test_api_node_boats_e2e_mutations.py scripts/api_node_boats_e2e_mutations.py
git commit -m "feat: add evidence-bearing mutations for api-node-boats e2e scan phase"
```

## Chunk 4: End-to-End Harness and Compose Wrapper

### Task 7: Add the failing end-to-end Python harness test

**Files:**
- Create: `tests/e2e/test_api_node_boats_reindex_compose.py`
- Reference: `tests/e2e/test_relationship_platform_compose.py`

- [ ] **Step 1: Write the failing test**

```python
def test_api_node_boats_reindex_compose_flow(...) -> None:
    ...
```

The test should:
- load a local-only manifest path from env
- skip if the manifest path is absent
- exercise:
  - bootstrap contract
  - scan mutation phase
  - post-scan contract

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/e2e/test_api_node_boats_reindex_compose.py -q`
Expected: FAIL because the harness script and fixtures do not exist yet.

- [ ] **Step 3: Write minimal implementation**

**Files:**
- Create: `scripts/run_api_node_boats_e2e.py`
- Modify: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_api_node_boats_reindex_compose.py`

Implement:
- generic orchestrator script that:
  - reads local manifest
  - clones missing repos
  - creates disposable remotes and working copies
  - stages the bootstrap workspace
  - drives the HTTP validation cycle
  - applies mutations, pushes, calls scan, and validates post-scan deltas
- e2e fixtures for invoking that orchestrator against the live compose stack

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/e2e/test_api_node_boats_reindex_compose.py -q`
Expected: PASS with a local manifest configured.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_api_node_boats_reindex_compose.py tests/e2e/conftest.py scripts/run_api_node_boats_e2e.py
git commit -m "feat: add api-node-boats compose reindex e2e harness"
```

### Task 8: Add the compose wrapper and operator ergonomics

**Files:**
- Create: `scripts/verify_api_node_boats_reindex_compose.sh`
- Modify: `docs/docs/deployment/docker-compose.md`

- [ ] **Step 1: Write the failing shell validation test or smoke expectation**

Document the expected command and env contract:

```bash
PCG_LOCAL_ECOSYSTEM_MANIFEST=~/api-node-boats-ecosystem.yaml \
./scripts/verify_api_node_boats_reindex_compose.sh
```

- [ ] **Step 2: Run syntax and smoke checks to verify they fail**

Run: `bash -n scripts/verify_api_node_boats_reindex_compose.sh`
Expected: FAIL because the wrapper does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement wrapper behavior mirroring the existing compose scripts:
- choose free ports
- start compose
- wait for bootstrap/API health
- read API key
- run the new e2e pytest
- print:
  - failing repo ids
  - useful compose logs
  - manifest path
  - temp workspace path
  - Jaeger URL

- [ ] **Step 4: Run checks to verify it passes**

Run:
- `bash -n scripts/verify_api_node_boats_reindex_compose.sh`
- `PCG_LOCAL_ECOSYSTEM_MANIFEST=~/api-node-boats-ecosystem.yaml ./scripts/verify_api_node_boats_reindex_compose.sh`

Expected: syntax passes, then the full local flow passes with a valid local-only manifest.

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_api_node_boats_reindex_compose.sh docs/docs/deployment/docker-compose.md
git commit -m "feat: add api-node-boats compose verification wrapper"
```

## Chunk 5: Final Verification and Cleanup

### Task 9: Run focused verification before broader execution

**Files:**
- Verify: `scripts/api_node_boats_e2e_manifest.py`
- Verify: `scripts/api_node_boats_e2e_workspace.py`
- Verify: `scripts/api_node_boats_e2e_git_runtime.py`
- Verify: `scripts/api_node_boats_e2e_clone_support.py`
- Verify: `scripts/api_node_boats_e2e_http_contract.py`
- Verify: `scripts/api_node_boats_e2e_mutations.py`
- Verify: `scripts/run_api_node_boats_e2e.py`
- Verify: `tests/e2e/test_api_node_boats_reindex_compose.py`

- [ ] **Step 1: Run focused unit tests**

Run:

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/scripts/test_api_node_boats_e2e_manifest.py \
  tests/unit/scripts/test_api_node_boats_e2e_workspace.py \
  tests/unit/scripts/test_api_node_boats_e2e_git_runtime.py \
  tests/unit/scripts/test_api_node_boats_e2e_clone_support.py \
  tests/unit/scripts/test_api_node_boats_e2e_http_contract.py \
  tests/unit/scripts/test_api_node_boats_e2e_mutations.py -q
```

Expected: PASS

- [ ] **Step 2: Run the compose-backed end-to-end flow**

Run:

```bash
PCG_LOCAL_ECOSYSTEM_MANIFEST=~/api-node-boats-ecosystem.yaml \
./scripts/verify_api_node_boats_reindex_compose.sh
```

Expected: PASS

- [ ] **Step 3: Run Python hygiene checks**

Run:

```bash
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
```

Expected: PASS

- [ ] **Step 4: Commit the final integration slice**

```bash
git add scripts tests docs
git commit -m "feat: add local api-node-boats full reindex verification harness"
```
