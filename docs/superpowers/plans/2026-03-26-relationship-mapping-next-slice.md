# Relationship Mapping Next Slice Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the next typed ArgoCD relationship semantic (`DEPLOYS_FROM`), verify it end to end, and capture the current mapping output from the local corpus.

**Architecture:** Extend raw ArgoCD file evidence extraction so ApplicationSet template sources can emit deploy-source evidence in addition to config-discovery evidence. Keep the existing resolver pipeline, typed-edge precedence, JSON logging, and OTEL tracing intact, then validate the new mapping with focused tests and an end-to-end corpus run.

**Tech Stack:** Python, pytest, Neo4j, PostgreSQL, Docker Compose, OpenTelemetry, MkDocs

---

## Chunk 1: Behavior Change

### Task 1: Add failing tests for `DEPLOYS_FROM`

**Files:**
- Modify: `tests/unit/relationships/test_file_evidence.py`
- Modify: `tests/unit/relationships/test_resolver.py`

- [ ] **Step 1: Write the failing file-evidence test**

Add a test that builds:
- one ArgoCD repo checkout
- one target repo checkout for `helm-charts`
- an `ApplicationSet` YAML with:
  - generator `git.files[].path` for config discovery
  - template `spec.source.repoURL` or `spec.sources[].repoURL` pointing at `helm-charts`

Expect:
- one `ARGOCD_APPLICATIONSET_DISCOVERY` fact with `DISCOVERS_CONFIG_IN`
- one new deploy-source fact with `DEPLOYS_FROM`

- [ ] **Step 2: Run the new file-evidence test to verify it fails**

Run:
```bash
PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_file_evidence.py -q
```

Expected:
- the new `DEPLOYS_FROM` assertion fails because the extractor does not emit it yet

- [ ] **Step 3: Write the failing resolver/projection test**

Add a test that proves:
- `DEPLOYS_FROM` survives resolution as a typed edge
- projection writes `MERGE (source)-[rel:DEPLOYS_FROM]->(target)`

- [ ] **Step 4: Run the resolver test to verify it fails**

Run:
```bash
PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_resolver.py -q
```

Expected:
- failure because no `DEPLOYS_FROM` relationship is produced or projected yet

### Task 2: Implement `DEPLOYS_FROM` evidence extraction for ArgoCD

**Files:**
- Modify: `src/platform_context_graph/relationships/file_evidence.py`
- Test: `tests/unit/relationships/test_file_evidence.py`

- [ ] **Step 1: Implement minimal extractor support**

In `file_evidence.py`:
- keep the existing ApplicationSet discovery extractor
- add extraction of deploy-source repo URLs from:
  - `spec.template.spec.source.repoURL`
  - `spec.template.spec.sources[].repoURL`
- emit a new evidence fact for matched repos:
  - `evidence_kind="ARGOCD_APPLICATIONSET_DEPLOY_SOURCE"`
  - `relationship_type="DEPLOYS_FROM"`
  - confidence near the existing ArgoCD typed evidence
  - rationale describing that ArgoCD deploys from the target repository
- include explainable details:
  - `repo_url`
  - source path if present
  - extractor name
  - file path

- [ ] **Step 2: Keep observability aligned**

Update the ArgoCD file-evidence span/log bookkeeping to include deploy-source counts without breaking the existing JSON envelope or OTEL attributes.

- [ ] **Step 3: Run the focused file-evidence tests**

Run:
```bash
PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_file_evidence.py -q
```

Expected:
- the new ArgoCD file-evidence test passes

### Task 3: Ensure resolver and projection handle `DEPLOYS_FROM`

**Files:**
- Modify: `src/platform_context_graph/relationships/resolver.py`
- Modify: `src/platform_context_graph/relationships/execution.py`
- Test: `tests/unit/relationships/test_resolver.py`

- [ ] **Step 1: Verify minimal resolver behavior**

Keep typed-edge behavior consistent:
- `DEPLOYS_FROM` should resolve as a typed edge
- generic `DEPENDS_ON` for the same pair should remain suppressed if present
- `DISCOVERS_CONFIG_IN` and `DEPLOYS_FROM` may coexist for the same pair because they are not generic fallbacks

- [ ] **Step 2: Verify projection behavior**

Ensure the resolved graph projection emits `DEPLOYS_FROM` safely using the existing relationship-type validation.

- [ ] **Step 3: Run the resolver tests**

Run:
```bash
PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/relationships/test_resolver.py -q
```

Expected:
- the new typed-edge tests pass

## Chunk 2: Documentation And Verification

### Task 4: Update the relationship docs for implemented `DEPLOYS_FROM`

**Files:**
- Modify: `docs/docs/reference/relationship-mapping.md`
- Modify: `src/platform_context_graph/relationships/README.md`

- [ ] **Step 1: Update examples from planned to implemented where appropriate**

Document that ArgoCD can now emit both:
- `DISCOVERS_CONFIG_IN`
- `DEPLOYS_FROM`

- [ ] **Step 2: Keep the extension guidance for GitHub Actions and FluxCD consistent**

Make sure the decision rules still say:
- config scanning => `DISCOVERS_CONFIG_IN`
- actual deploy source => `DEPLOYS_FROM`

### Task 5: Run focused verification

**Files:**
- Verify only

- [ ] **Step 1: Run the focused relationship suite**

Run:
```bash
PYTHONPATH=src uv run --extra dev python -m pytest \
  tests/unit/relationships/test_file_evidence.py \
  tests/unit/relationships/test_resolver.py \
  tests/unit/indexing/test_coordinator_pipeline.py \
  tests/integration/cli/test_cli_commands.py -q
```

- [ ] **Step 2: Run docs build**

Run:
```bash
uvx --with mkdocs-material mkdocs build -f docs/mkdocs.yml
```

## Chunk 3: End-To-End Mapping Run

### Task 6: Run the local corpus end to end and capture mappings

**Files:**
- Verify only

- [ ] **Step 1: Use the reduced Mobius corpus to prove the typed chain end to end**

Run the local bootstrap corpus with Docker Compose or the established local runtime path.

Target outcomes:
- active generation created successfully
- `DISCOVERS_CONFIG_IN` edges present
- `DEPLOYS_FROM` edge present for ArgoCD deploy sources
- multi-hop chain visible from `iac-eks-argocd`

- [ ] **Step 2: Attempt the larger corpus with lower concurrency**

If machine resources allow, rerun the broader corpus with:
- `PCG_PARSE_WORKERS=1`
- `PCG_INDEX_QUEUE_DEPTH=2`

If the machine still cannot complete it, document the environment limitation explicitly and report the reduced-corpus end-to-end result as the verified mapping baseline.

- [ ] **Step 3: Summarize exact mappings**

Report:
- generation id
- candidate and resolved counts
- typed edges
- generic fallback edges still present
- unmatched control pair results

