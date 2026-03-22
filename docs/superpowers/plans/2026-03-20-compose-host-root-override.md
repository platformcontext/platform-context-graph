# Compose Host Root Override Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a checked-in Docker Compose host-root override so local E2E runs can index an arbitrary host directory while the default remains fixture-backed.

**Architecture:** Keep the container-side runtime path fixed at `/fixtures` and make only the host side of the bind mount configurable through `PCG_FILESYSTEM_HOST_ROOT`. Validate the rendered Compose config in tests and document the override for local E2E runs.

**Tech Stack:** Docker Compose, pytest, YAML deployment assets, Markdown docs

---

## Chunk 1: Red-Green Compose Override

### Task 1: Add a failing deployment rendering test

**Files:**
- Modify: `tests/integration/deployment/test_public_deployment_assets.py`
- Test: `tests/integration/deployment/test_public_deployment_assets.py`

- [ ] **Step 1: Write the failing test**
Add a test that runs `docker-compose -f docker-compose.yaml config` with `PCG_FILESYSTEM_HOST_ROOT=/tmp/pcg-host-root` and asserts that the rendered `bootstrap-index` and `repo-sync` volumes include `/tmp/pcg-host-root:/fixtures:ro`.

- [ ] **Step 2: Run test to verify it fails**
Run: `PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -k filesystem_host_root -q`
Expected: FAIL because the current compose files still hardcode `./tests/fixtures/ecosystems:/fixtures:ro`.

- [ ] **Step 3: Write minimal implementation**
Update `docker-compose.yaml` and `docker-compose.template.yml` to use `${PCG_FILESYSTEM_HOST_ROOT:-./tests/fixtures/ecosystems}:/fixtures:ro` for the `bootstrap-index` and `repo-sync` mounts.

- [ ] **Step 4: Run test to verify it passes**
Run: `PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -k filesystem_host_root -q`
Expected: PASS.

### Task 2: Document the override

**Files:**
- Modify: `docs/docs/deployment/docker-compose.md`

- [ ] **Step 1: Update docs**
Document the default fixture-backed behavior and show a real local E2E invocation using `PCG_FILESYSTEM_HOST_ROOT="$HOME/repos/mobius" docker compose up --build`.

- [ ] **Step 2: Verify docs-focused test scope**
Run: `PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -q`
Expected: PASS.

## Chunk 2: Local E2E Verification

### Task 3: Run the local E2E stack against Mobius

**Files:**
- Modify: `docker-compose.yaml`
- Modify: `docker-compose.template.yml`
- Modify: `docs/docs/deployment/docker-compose.md`
- Test: live local stack

- [ ] **Step 1: Start from a clean stack**
Run: `docker-compose down -v`

- [ ] **Step 2: Start with the host-root override**
Run: `PCG_FILESYSTEM_HOST_ROOT="$HOME/repos/mobius" docker-compose up -d --build`

- [ ] **Step 3: Verify bootstrap and service health**
Run:
  - `docker-compose ps`
  - `docker-compose logs --tail=200 bootstrap-index`
  - `docker-compose logs --tail=200 repo-sync`
  - `docker-compose logs --tail=200 platform-context-graph`

- [ ] **Step 4: Verify live API behavior**
Run:
  - `curl -fsS http://localhost:8080/health`
  - `curl -fsS http://localhost:8080/api/v0/repositories`
  - representative content routes using real indexed data

- [ ] **Step 5: Run broader repository verification**
Run:
  - `python3 scripts/check_python_file_lengths.py --max-lines 500`
  - `python3 scripts/check_python_docstrings.py`
  - `PYTHONPATH=src uv run python -m pytest tests/unit tests/integration/api tests/integration/mcp/test_mcp_server.py tests/integration/cli/test_cli_commands.py tests/integration/docs tests/integration/deployment/test_public_deployment_assets.py -q`
  - `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml`

- [ ] **Step 6: Do not commit until all verification is green**
The user’s acceptance gate is a clean local build and end-to-end verification against `~/repos/mobius`.
