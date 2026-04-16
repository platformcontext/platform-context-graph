# Projector Reducer Parser Relationship Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the newly verified correctness and parity gaps in projector and reducer execution, canonical relationship materialization, and parser-family-to-graph wiring so the Go platform matches the intended PCG workflow honestly.

**Architecture:** Keep the existing Go-owned service boundaries intact, but harden the state machines and edge-writing semantics where the audit found correctness gaps. Promote parser families only when they become durable facts, reducer-owned canonical edges, and query-visible relationship surfaces instead of staying as parser-only metadata or query fallbacks.

**Tech Stack:** Go, PostgreSQL, Neo4j, OpenTelemetry, structured JSON logging, Docker Compose, Helm, MkDocs

---

## Scope And Current Truth

The audit on 2026-04-16 verified five classes of gaps that now supersede the
older parity docs:

1. projector and reducer lease expiry does not requeue expired claimed work
2. shared projection retract/write/complete is not crash-safe and has no poison
   intent quarantine path
3. typed IaC relationships are flattened in canonical graph materialization,
   and ArgoCD destination `RUNS_ON` does not survive into the canonical graph
4. repo-level read models underreport platform ownership because they query the
   wrong edge shape
5. several parser families stop at parser metadata instead of becoming
   canonical relationship truth:
   - Terraform `*.tfvars` and `*.tfvars.json`
   - Jenkins and Groovy pipeline metadata
   - Ansible automation and inventory semantics
   - Docker and Docker Compose relationship semantics
   - GitHub Actions relationship semantics

This plan fixes those gaps in-place on the current branch. It does not reopen
the Python migration itself. It hardens and completes the Go-owned path.

## Files And Responsibilities

### Runtime and queue lifecycle

- Modify: `go/internal/storage/postgres/projector_queue.go`
- Modify: `go/internal/storage/postgres/reducer_queue.go`
- Modify: `go/internal/storage/postgres/reducer_queue_batch.go`
- Modify: `go/internal/storage/postgres/recovery.go`
- Modify: `go/internal/storage/postgres/status.go`
- Modify: `go/internal/status/status.go`
- Modify: `go/internal/projector/service.go`
- Modify: `go/internal/reducer/service.go`
- Test: `go/internal/storage/postgres/*queue*_test.go`
- Test: `go/internal/projector/*test.go`
- Test: `go/internal/reducer/*test.go`

### Shared projection crash-safety and poison-intent handling

- Modify: `go/internal/reducer/shared_projection_worker.go`
- Modify: `go/internal/reducer/shared_projection_runner.go`
- Modify: `go/internal/storage/postgres/shared_intents.go`
- Modify: `go/internal/storage/neo4j/edge_writer.go`
- Modify: `go/internal/storage/neo4j/canonical.go`
- Test: `go/internal/reducer/shared_projection_*test.go`
- Test: `go/internal/storage/postgres/shared_intents_test.go`
- Test: `go/internal/storage/neo4j/edge_writer*_test.go`

### Canonical relationship fidelity and read-model repair

- Modify: `go/internal/reducer/cross_repo_resolution.go`
- Modify: `go/internal/storage/neo4j/edge_writer.go`
- Modify: `go/internal/storage/neo4j/canonical.go`
- Modify: `go/internal/relationships/resolver.go`
- Modify: `go/internal/relationships/models.go`
- Modify: `go/internal/relationships/yaml_iac_evidence.go`
- Modify: `go/internal/query/repository.go`
- Modify: `go/internal/query/entity.go`
- Test: `go/internal/reducer/cross_repo_resolution_test.go`
- Test: `go/internal/storage/neo4j/edge_writer*_test.go`
- Test: `go/internal/query/repository*_test.go`
- Test: `go/internal/query/entity*_test.go`
- Test: `go/internal/relationships/*test.go`

### Parser family promotion to durable graph truth

- Modify: `go/internal/parser/registry.go`
- Modify: `go/internal/parser/templated_detection.go`
- Modify: `go/internal/parser/groovy_language.go`
- Modify: `go/internal/parser/dockerfile_language.go`
- Modify: `go/internal/parser/yaml_language.go`
- Modify: `go/internal/parser/raw_text_engine.go`
- Modify: `go/internal/collector/git_snapshot_native.go`
- Modify: `go/internal/collector/git_fact_builder.go`
- Modify: `go/internal/content/shape/materialize.go`
- Modify: `go/internal/relationships/evidence.go`
- Modify: `go/internal/relationships/yaml_iac_evidence.go`
- Modify: `go/internal/reducer/candidate_loader.go`
- Modify: `go/internal/reducer/infrastructure_platform_extractor.go`
- Modify: `go/internal/query/content_relationships.go`
- Add or split as needed:
  - `go/internal/relationships/github_actions_evidence.go`
  - `go/internal/relationships/docker_evidence.go`
  - `go/internal/relationships/groovy_ci_evidence.go`
  - `go/internal/relationships/ansible_evidence.go`
- Test:
  - `go/internal/parser/*test.go`
  - `go/internal/collector/*test.go`
  - `go/internal/content/shape/*test.go`
  - `go/internal/relationships/*test.go`
  - `go/internal/reducer/*test.go`
  - `go/internal/query/*test.go`

### Documentation and parity truth reset

- Modify: `docs/docs/reference/python-to-go-parity.md`
- Modify: `docs/docs/reference/parity-closure-matrix.md`
- Modify: `docs/docs/reference/merge-readiness-signoff.md`
- Modify: `docs/docs/reference/relationship-mapping.md`
- Modify: `docs/docs/reference/local-testing.md`
- Modify: `docs/docs/reference/telemetry/index.md`
- Modify: `docs/docs/languages/groovy.md`
- Modify: `docs/docs/use-cases.md`
- Modify: `docs/docs/deployment/service-runtimes.md`
- Modify: `docs/superpowers/plans/2026-04-14-go-parity-closure-plan.md`

## Chunk 1: Reset Branch Truth And Add Regression Fence

### Goal

Make the docs and parity records honest again before new fixes land, and add a
checked-in execution record for the newly discovered gaps.

### Ownership impact

- runtime ownership: no
- parser ownership: no
- reducer/projector ownership: no
- query ownership: no
- docs truth: yes

### Parallel subagent wave

- Agent A: rewrite parity docs and matrix to `partial` or `fail` for the newly
  verified gaps
- Agent B: update relationship-mapping and local-testing docs to include the
  missing validation expectations for shared projection, typed edges, and
  GitHub Actions / Jenkins / Ansible / Docker families

### Tasks

- [ ] **Step 1: Update branch-truth docs with the new audited gaps**

Modify the docs listed above so they stop claiming full parity on the affected
surfaces.

- [ ] **Step 2: Add this plan to the active execution record**

Link this plan from the relevant parity and doc-index pages.

- [ ] **Step 3: Verify docs build cleanly**

Run: `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml`
Expected: PASS

- [ ] **Step 4: Commit**

Commit message: `docs(parity): reset projector reducer relationship truth`

## Chunk 2: Queue Lease Recovery And Ack Failure Visibility

### Goal

Make projector and reducer work reclaimable after worker crashes or ack
failures, and expose those failures in structured telemetry and status.

### Delete, replace, or migrate

- replace the “expired claim but never reclaim” state machine
- replace silent ack-failure visibility gaps with explicit structured telemetry
- keep the same queue tables and ownership boundaries

### Ownership impact

- runtime ownership: yes
- parser ownership: no
- reducer/projector ownership: yes
- query ownership: status only

### Parallel subagent wave

- Agent A: projector queue claim-recovery and projector service telemetry
- Agent B: reducer queue claim-recovery, batch-claim recovery, and reducer
  service telemetry

### Tasks

- [ ] **Step 1: Write failing queue recovery tests**

Add focused tests proving expired `claimed` rows are reclaimable for:
- projector single-claim path
- reducer single-claim path
- reducer batch-claim path

- [ ] **Step 2: Run the focused tests to confirm failure**

Run:
- `go test ./go/internal/storage/postgres -run 'Test(ProjectorQueue|ReducerQueue).*Expired'`
Expected: FAIL

- [ ] **Step 3: Update claim SQL to reclaim expired leases**

Treat expired `claimed` rows the same as eligible retry work, preserving
attempt accounting and visibility semantics.

- [ ] **Step 4: Write failing telemetry/status tests for ack failures**

Add tests proving ack failures emit structured error logs and failure counters
instead of disappearing from the normal success/failure accounting.

- [ ] **Step 5: Implement projector/reducer service telemetry updates**

Ensure ack errors are recorded with queue/domain/stage context in JSON logs and
OTel counters/histograms.

- [ ] **Step 6: Run focused tests**

Run:
- `go test ./go/internal/storage/postgres ./go/internal/projector ./go/internal/reducer`
Expected: PASS

- [ ] **Step 7: Run lint on touched packages**

Run:
- `golangci-lint run ./go/internal/storage/postgres/... ./go/internal/projector/... ./go/internal/reducer/...`
Expected: PASS

- [ ] **Step 8: Commit**

Commit message: `fix(queue): reclaim expired projector and reducer claims`

## Chunk 3: Shared Projection Crash Safety And Poison Intent Handling

### Goal

Make shared projection safe under process death and repeated bad input.

### Delete, replace, or migrate

- replace best-effort retract/write/complete sequencing with crash-safe
  semantics
- replace infinite retry churn with an explicit quarantine or failure state for
  poisoned shared intents

### Ownership impact

- runtime ownership: yes
- parser ownership: no
- reducer/projector ownership: yes
- neo4j write semantics: yes

### Parallel subagent wave

- Agent A: shared intent store lifecycle and poison-intent state model
- Agent B: Neo4j edge-writer transaction boundary and shared worker sequencing

### Tasks

- [ ] **Step 1: Write failing shared-projection crash-safety tests**

Cover:
- retract succeeds, write fails
- write succeeds, mark-complete fails
- partition run retries stale work without duplicating or losing graph truth

- [ ] **Step 2: Write failing poison-intent lifecycle tests**

Cover:
- repeated deterministic bad payload transitions to terminal/quarantined state
- runner surfaces failure metrics and logs

- [ ] **Step 3: Implement shared-intent failure lifecycle**

Add durable status and attempt metadata to the shared-intent store, or another
equally explicit terminal path, without collapsing service boundaries.

- [ ] **Step 4: Make retract/write/complete crash-safe**

Prefer one of:
- atomic transactional sequencing in the writer boundary
- explicit two-phase/idempotent sequencing with durable execution markers

Do not leave “retry and hope” semantics in place.

- [ ] **Step 5: Run focused tests**

Run:
- `go test ./go/internal/reducer -run 'TestSharedProjection|TestProcessPartitionOnce'`
- `go test ./go/internal/storage/postgres -run 'TestSharedIntent'`
- `go test ./go/internal/storage/neo4j -run 'TestEdgeWriter'`
Expected: PASS

- [ ] **Step 6: Run lint**

Run:
- `golangci-lint run ./go/internal/reducer/... ./go/internal/storage/postgres/... ./go/internal/storage/neo4j/...`
Expected: PASS

- [ ] **Step 7: Commit**

Commit message: `fix(reducer): harden shared projection execution semantics`

## Chunk 4: Typed Relationship Fidelity And Read-Model Repair

### Goal

Preserve typed IaC relationships in the canonical graph, materialize ArgoCD
destination `RUNS_ON`, and repair repo-level read models to reflect actual
graph shape.

### Delete, replace, or migrate

- replace flattened `DEPENDS_ON` output with typed canonical edge writes where
  the resolver already knows the relationship family
- migrate ArgoCD destination platform evidence from query fallback into
  canonical graph truth
- replace repo-level `RUNS_ON` queries that assume the wrong source node shape

### Ownership impact

- runtime ownership: yes
- parser ownership: no
- reducer ownership: yes
- query ownership: yes

### Parallel subagent wave

- Agent A: typed edge preservation and Neo4j writer changes
- Agent B: ArgoCD destination `RUNS_ON` canonicalization
- Agent C: repo story/context/read-model correction

### Tasks

- [ ] **Step 1: Write failing resolution and edge-writer tests**

Cover:
- `PROVISIONS_DEPENDENCY_FOR` survives materialization
- `DEPLOYS_FROM` survives materialization
- `DISCOVERS_CONFIG_IN` survives materialization
- ArgoCD destination `RUNS_ON` becomes a canonical graph edge

- [ ] **Step 2: Write failing query tests**

Cover:
- repo context/story platform counts from workload-instance `RUNS_ON`
- typed relationship visibility in repo/query responses

- [ ] **Step 3: Implement typed edge preservation**

Carry relationship type through reducer rows and the Neo4j writer instead of
flattening to generic repo dependency semantics.

- [ ] **Step 4: Implement ArgoCD destination platform materialization**

Ensure destination evidence becomes canonical graph truth, not only query-time
fallback.

- [ ] **Step 5: Repair repo-level graph reads**

Read actual workload-instance-to-platform shape, or otherwise compute repo
platform signals truthfully from canonical graph state.

- [ ] **Step 6: Run focused tests**

Run:
- `go test ./go/internal/relationships ./go/internal/reducer ./go/internal/storage/neo4j ./go/internal/query`
Expected: PASS

- [ ] **Step 7: Run lint**

Run:
- `golangci-lint run ./go/internal/relationships/... ./go/internal/reducer/... ./go/internal/storage/neo4j/... ./go/internal/query/...`
Expected: PASS

- [ ] **Step 8: Commit**

Commit message: `fix(relationships): preserve typed canonical edge fidelity`

## Chunk 5: Parser Family Promotion For IaC And CI/CD Relationship Truth

### Goal

Promote the missing parser families from “parsed metadata” to durable facts,
canonical relationship materialization, and query-visible graph truth.

### Delete, replace, or migrate

- replace parser-only CI/CD metadata with reducer- and query-backed graph
  semantics
- replace hidden `.tfvars` exclusion with normal-path collector support
- add GitHub Actions as a first-class relationship-mapping family

### Ownership impact

- parser ownership: yes
- collector ownership: yes
- reducer ownership: yes
- query ownership: yes

### Parallel subagent wave

- Agent A: Terraform `tfvars` reachability and HCL-family collector support
- Agent B: Jenkins/Groovy and Ansible relationship evidence/materialization
- Agent C: Docker and Docker Compose relationship evidence/materialization
- Agent D: GitHub Actions relationship evidence, canonicalization, and query
  surfacing

### Tasks

- [ ] **Step 1: Write failing parser and collector tests**

Cover:
- `.tfvars` and `.tfvars.json` survive registry lookup and collector discovery
- Groovy/Jenkins metadata persists through content shaping
- Ansible path families become durable entities or evidence-bearing content
- Docker and Docker Compose emit relationship-bearing metadata
- GitHub Actions workflow files become relationship-bearing content

- [ ] **Step 2: Write failing relationship and query tests**

Cover:
- Jenkins and Ansible controller-driven relationships
- Docker and Docker Compose `DEPLOYS_FROM` or equivalent deployment-source
  semantics where Python previously implied them
- GitHub Actions relationships into repositories, workflow subjects,
  deployment/config discovery, or other explicitly modeled PCG semantics

- [ ] **Step 3: Implement collector reachability fixes**

Register and retain the missing file families in the normal path, including
Terraform variable files.

- [ ] **Step 4: Implement evidence extraction and reducer-facing payloads**

Add focused relationship discovery helpers for:
- Jenkins and Groovy
- Ansible
- Docker and Docker Compose
- GitHub Actions

Keep each family in a focused file under `go/internal/relationships/`.

- [ ] **Step 5: Implement content shaping and query surfacing**

Persist the relationship-relevant metadata and expose it through normal query
surfaces, not only fallback or docs promises.

- [ ] **Step 6: Run focused tests**

Run:
- `go test ./go/internal/parser ./go/internal/collector ./go/internal/content/shape ./go/internal/relationships ./go/internal/reducer ./go/internal/query`
Expected: PASS

- [ ] **Step 7: Run lint**

Run:
- `golangci-lint run ./go/internal/parser/... ./go/internal/collector/... ./go/internal/content/... ./go/internal/relationships/... ./go/internal/reducer/... ./go/internal/query/...`
Expected: PASS

- [ ] **Step 8: Commit**

Commit message: `feat(parsers): promote iac and ci cd relationships to graph truth`

## Chunk 6: End-To-End Validation And Documentation Lock

### Goal

Re-prove the corrected behavior through local validation and update parity docs
to the new post-fix truth.

### Ownership impact

- docs truth: yes
- runtime validation: yes
- deployment verification: yes

### Parallel subagent wave

- Agent A: docs lock and parity matrix update after code lands
- Agent B: compose-backed and API/query validation

### Tasks

- [ ] **Step 1: Update parity docs to the new verified truth**

Only flip rows back to `pass` where parser, persistence, reducer, query, and
docs all agree.

- [ ] **Step 2: Run focused Go tests for touched packages**

Run:
- `go test ./go/internal/storage/postgres ./go/internal/projector ./go/internal/reducer ./go/internal/relationships ./go/internal/storage/neo4j ./go/internal/query ./go/internal/parser ./go/internal/collector ./go/internal/content/shape`
Expected: PASS

- [ ] **Step 3: Run lint and vet**

Run:
- `golangci-lint run ./go/...`
- `go vet ./go/...`
Expected: PASS

- [ ] **Step 4: Run docs build**

Run:
- `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml`
Expected: PASS

- [ ] **Step 5: Run repo hygiene checks**

Run:
- `git diff --check`
Expected: PASS

- [ ] **Step 6: Commit**

Commit message: `docs(parity): lock projector reducer relationship truth`

## Recommended Execution Order

1. Chunk 1
2. Chunk 2 and Chunk 4 in parallel
3. Chunk 3 after queue semantics are stable
4. Chunk 5 after typed relationship fidelity is in place
5. Chunk 6 last

## Recommended Subagent Waves

### Wave 1

- docs truth reset
- queue recovery design review
- typed relationship write-path design review

### Wave 2

- projector lease recovery implementation
- reducer lease recovery implementation
- typed edge preservation implementation
- repo read-model repair

### Wave 3

- shared projection crash-safety
- shared intent poison-state handling

### Wave 4

- Terraform `tfvars` reachability
- Jenkins and Groovy relationship promotion
- Ansible relationship promotion
- Docker and Docker Compose relationship promotion
- GitHub Actions relationship promotion

### Wave 5

- docs lock
- compose and API validation
- parity matrix final pass

## Exit Criteria

Do not mark this plan complete until all of the following are true:

- expired `claimed` projector and reducer work is reclaimable
- shared projection has a crash-safe execution model and poison intent path
- typed IaC relationships survive canonical graph materialization without
  flattening
- ArgoCD destination `RUNS_ON` survives as canonical graph truth
- repo-level platform context reflects actual graph shape
- Terraform `tfvars`, Jenkins, Ansible, Docker, Docker Compose, and GitHub
  Actions are either fully promoted into relationship mapping or explicitly
  documented as intentional non-goals
- parity docs no longer overstate completion
- focused tests, `golangci-lint`, `go vet`, docs build, and `git diff --check`
  all pass

## Source Of Truth

Track completion against:

- `docs/docs/reference/python-to-go-parity.md`
- `docs/docs/reference/parity-closure-matrix.md`
- `docs/docs/reference/relationship-mapping.md`
- `docs/docs/reference/merge-readiness-signoff.md`
- this plan
