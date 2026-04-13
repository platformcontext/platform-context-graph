# Milestone 1 Completion Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Milestone 1 so the Go data plane has a fully native Git proof path, live operator proof for collector/projector/reducer, and explicit local validation and docs.

**Architecture:** Milestone 1 stays bounded to the Git-backed proof path. The collector must stop depending on the Python snapshot bridge for core correctness, while projector and reducer must each have a runnable compose-backed proof with the shared admin/status contract and real durable queue behavior. We do not expand Milestone 1 into canonical cross-source truth or future cloud collectors.

**Tech Stack:** Go runtimes, Postgres, Neo4j, Docker Compose, pytest e2e harnesses, OTEL/Prometheus runtime wiring, MkDocs docs.

---

## Completion Standard

Milestone 1 is complete only when all of the following are true:

- `collector-git` owns the bounded Git proof path natively without Python subprocess dependency for core collection and fact shaping
- `projector` has a compose-backed runtime proof with `/healthz`, `/readyz`, `/admin/status`, and real queue consumption
- `reducer` has a compose-backed runtime proof with `/healthz`, `/readyz`, `/admin/status`, and real queue drain behavior
- long-running Go services expose real runtime metrics and OTEL bootstrap instead of contract-only placeholders
- local runbooks list the exact commands that prove Milestone 1 end to end

## Workstream Map

### Workstream A: Native Collector Cutover

**Purpose:** Remove the Python snapshot bridge from the collector hot path and move bounded Git snapshot collection into Go-owned code.

**Primary files:**
- Modify: `go/cmd/collector-git/service.go`
- Modify: `go/internal/collector/`
- Modify: `go/internal/compatibility/pythonbridge/collector_git.go`
- Modify: `go/internal/compatibility/pythonbridge/snapshot_git.go`
- Modify or retire: `src/platform_context_graph/runtime/ingester/go_collector_bridge.py`
- Modify or retire: `src/platform_context_graph/runtime/ingester/go_collector_snapshot_bridge.py`
- Test: `go/internal/collector/*_test.go`
- Test: `go/internal/compatibility/pythonbridge/*_test.go`

- [ ] **Step 1: Lock the bounded native collector contract**

Document the exact bounded native output required from the Go collector:
- scope
- generation
- repository fact
- file/content/content-entity facts
- shared follow-up facts

Record whether any Python parsing remains temporarily allowed and where.

- [ ] **Step 2: Write or extend failing Go tests for native Git snapshot collection**

Add or extend collector tests so a native Go path must:
- select repositories
- parse supported files for the bounded proof path
- emit the same fact families that the bridge proof currently emits

Run: `cd go && go test ./internal/collector ./cmd/collector-git -count=1`
Expected: failing coverage for the new native path before implementation.

- [ ] **Step 3: Implement the native collector path**

Move the bounded proof path into Go-owned code and update `collector-git` wiring so the collector no longer depends on the Python bridge for core correctness.

- [ ] **Step 4: Narrow or retire bridge code**

If the bridge must remain temporarily, keep it isolated and explicitly transitional. If it is no longer needed for Milestone 1, remove it from the runtime hot path.

- [ ] **Step 5: Re-run collector verification**

Run:
- `cd go && go test ./internal/collector ./cmd/collector-git ./internal/compatibility/pythonbridge -count=1`
- `./scripts/verify_collector_git_runtime_compose.sh`

Expected: all passing, with the collector proof staying green after the cutover.

### Workstream B: Projector Runtime Proof

**Purpose:** Prove projector behavior live, not only through package-level tests.

**Primary files:**
- Modify: `go/cmd/projector/main.go`
- Modify: `go/cmd/projector/runtime_wiring.go`
- Modify if needed: `go/internal/storage/postgres/projector_queue.go`
- Modify if needed: `go/internal/storage/postgres/facts.go`
- Create: `scripts/verify_projector_runtime_compose.sh`
- Create: `tests/e2e/test_projector_runtime_compose.py`

- [ ] **Step 1: Write the failing e2e smoke test**

Add a compose-backed pytest that proves:
- `/healthz` returns 200
- `/readyz` returns 200
- `/admin/status?format=json` reports projector activity
- projector claims queued work and persists graph/content output for the bounded proof path

- [ ] **Step 2: Add the failing projector compose harness**

Create the runtime launcher script for local stack proof and run it once to capture the real failure.

Run: `./scripts/verify_projector_runtime_compose.sh`
Expected: fail before the service/harness is finished.

- [ ] **Step 3: Implement the minimal runtime and queue fixes**

Adjust projector runtime wiring, queue behavior, or proof setup until the bounded live proof works.

- [ ] **Step 4: Re-run projector gates**

Run:
- `cd go && go test ./cmd/projector ./internal/projector ./internal/storage/postgres -count=1`
- `PYTHONPATH=src uv run --extra dev pytest tests/e2e/test_projector_runtime_compose.py -q`
- `./scripts/verify_projector_runtime_compose.sh`

Expected: all passing.

### Workstream C: Reducer Runtime Proof

**Purpose:** Prove reducer behavior live with real queue claim, execution, and ack/fail semantics.

**Primary files:**
- Modify: `go/cmd/reducer/main.go`
- Modify if needed: `go/internal/reducer/`
- Modify if needed: `go/internal/storage/postgres/reducer_queue.go`
- Create: `scripts/verify_reducer_runtime_compose.sh`
- Create: `tests/e2e/test_reducer_runtime_compose.py`

- [ ] **Step 1: Write the failing reducer e2e smoke test**

Add a compose-backed pytest that proves:
- `/healthz` returns 200
- `/readyz` returns 200
- `/admin/status?format=json` reports reducer work
- reducer claims and drains queued reducer intents for the bounded proof domain

- [ ] **Step 2: Add the failing reducer compose harness**

Create the runtime launcher script and run it once to capture the real failure mode.

Run: `./scripts/verify_reducer_runtime_compose.sh`
Expected: fail before the runtime/harness is complete.

- [ ] **Step 3: Implement the minimal reducer runtime fixes**

Fix service wiring, queue behavior, or proof setup until the live reducer proof works.

- [ ] **Step 4: Re-run reducer gates**

Run:
- `cd go && go test ./cmd/reducer ./internal/reducer ./internal/storage/postgres -count=1`
- `PYTHONPATH=src uv run --extra dev pytest tests/e2e/test_reducer_runtime_compose.py -q`
- `./scripts/verify_reducer_runtime_compose.sh`

Expected: all passing.

### Workstream D: Telemetry And Metrics Wiring

**Purpose:** Turn the runtime observability contract into real service behavior.

**Primary files:**
- Modify: `go/internal/runtime/`
- Modify: `go/internal/telemetry/`
- Modify: `go/internal/app/`
- Modify: `go/cmd/collector-git/main.go`
- Modify: `go/cmd/projector/main.go`
- Modify: `go/cmd/reducer/main.go`
- Test: `go/internal/runtime/*_test.go`
- Test: `go/internal/telemetry/*_test.go`

- [ ] **Step 1: Write failing tests for runtime metrics and OTEL bootstrap**

Add or extend tests to require:
- mounted `/metrics` when configured
- real runtime metrics handler wiring
- OTEL bootstrap setup that is not just a frozen config object

- [ ] **Step 2: Implement runtime metrics and OTEL wiring**

Wire the shared metrics/admin surface and runtime telemetry bootstrap into the long-running commands.

- [ ] **Step 3: Re-run telemetry gates**

Run:
- `cd go && go test ./internal/runtime ./internal/telemetry ./internal/app -count=1`

Expected: passing with real runtime wiring.

### Workstream E: Milestone 1 Runbook And Exit Gate

**Purpose:** Make the milestone finish line explicit and repeatable.

**Primary files:**
- Modify: `docs/docs/reference/local-testing.md`
- Modify: `docs/docs/deployment/service-runtimes.md`
- Modify: `docs/docs/roadmap.md`
- Modify: `docs/superpowers/plans/2026-04-12-go-data-plane-milestone-01-native-git-cutover.md`

- [ ] **Step 1: Update the runbooks with the real proof commands**

Document the accepted Milestone 1 proof stack:
- collector proof
- projector proof
- reducer proof
- telemetry/admin checks

- [ ] **Step 2: Restate current status truthfully**

Update the milestone doc so it names what is complete, what is transitional, and what is now fully retired.

- [ ] **Step 3: Run doc verification**

Run:
- `git diff --check`
- `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml`

Expected: passing docs gate.

## Parallel Execution Plan

Use four worker tracks plus one integrator:

- Worker A owns Workstream A only
- Worker B owns Workstream B only
- Worker C owns Workstream C only
- Worker D owns Workstream D and supports Workstream E after code lands
- Main agent owns architecture decisions, review, integration, milestone validation, commit/push, PR updates, and final backlog reporting

## Final Milestone 1 Validation

Run this only after all workstreams are integrated:

```bash
cd go && go test ./internal/collector ./internal/projector ./internal/reducer ./internal/runtime ./internal/telemetry ./internal/storage/postgres ./cmd/collector-git ./cmd/projector ./cmd/reducer ./cmd/admin-status -count=1
```

```bash
PYTHONPATH=src uv run --extra dev pytest \
  tests/unit/compatibility/test_go_collector_snapshot_bridge.py \
  tests/e2e/test_collector_git_runtime_compose.py \
  tests/e2e/test_projector_runtime_compose.py \
  tests/e2e/test_reducer_runtime_compose.py -q
```

```bash
./scripts/verify_collector_git_runtime_compose.sh
./scripts/verify_projector_runtime_compose.sh
./scripts/verify_reducer_runtime_compose.sh
```

```bash
git diff --check
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

## Effort Summary

- Workstream A: `Large`
- Workstream B: `Medium`
- Workstream C: `Medium`
- Workstream D: `Medium`
- Workstream E: `Small`

## Notes

- Do not let Milestone 1 expand into canonical shared-truth graph modeling. That belongs to Milestone 3.
- Do not create new branches. Stay on `codex/go-data-plane-architecture`.
- Any remaining bridge code must be explicitly labeled transitional in docs and code.
