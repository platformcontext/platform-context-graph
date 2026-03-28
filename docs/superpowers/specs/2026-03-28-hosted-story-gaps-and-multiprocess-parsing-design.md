# Hosted Story Gaps And Multiprocess Parsing

## Summary

This design combines two related but independent workstreams:

- `workstream A`: close the hosted MCP/API story-completeness gaps surfaced by
  the `api-node-boats` investigation without requiring filesystem fallback
- `workstream B`: add a feature-flagged multiprocess parse engine so the
  indexing pipeline can parallelize CPU-bound parsing without fighting the GIL

This document explicitly challenges the source PRDs instead of treating them as
fully accurate:

- [`/Users/allen/pcg-tool-gaps-prd.md`](/Users/allen/pcg-tool-gaps-prd.md)
- [`/Users/allen/PRD-pcg-multiprocess-parsing.md`](/Users/allen/PRD-pcg-multiprocess-parsing.md)

It also extends, and does not replace, the existing prompt-contract design in
[2026-03-27-mcp-api-story-contract-design.md](2026-03-27-mcp-api-story-contract-design.md).

## Product Direction

PlatformContextGraph should answer hosted "tell me everything about this
service" questions using PCG surfaces alone. A user should not need raw Cypher,
server-local filesystem reads, or bash post-processing to understand Internet
to cloud to code.

At the same time, improving story completeness does not matter if indexing
latency remains dominated by CPU-bound parsing. The parsing engine must evolve
without changing graph correctness or destabilizing the existing async commit
pipeline.

The combined direction is:

- make story and support tools complete enough for hosted investigation flows
- make parse throughput scale beyond one Python interpreter
- keep these as separate workstreams with shared correctness and verification
  standards

## Inputs Challenged Against The Current Branch

### Hosted gap PRD

The hosted-gap PRD is directionally strong, but some findings are already stale
on this branch:

- `get_file_content` repo-name support is already fixed in the shared content
  query layer and covered by tests
- `get_index_status` repo-name resolution is already fixed, though one schema
  description still drifts from actual behavior
- `find_blast_radius` no longer returns the all-null placeholder row, but it
  still underuses richer consumer evidence already computed elsewhere
- `trace_deployment_chain` is already substantially filtered compared to the
  raw earlier behavior, but still lacks explicit output-shaping controls

The open hosted work should therefore focus on the residual gaps, not
re-implement already-landed fixes.

### Multiprocess parsing PRD

The multiprocessing PRD identifies a real architectural pressure point, but it
contains several claims that are not yet proven by repo-grounded measurement:

- exact parse-rate numbers
- exact CPU/core utilization ceilings
- exact time-split percentages between tree-sitter parse and Python traversal
- exact projected speedups for WordPress and other repos
- exact pod CPU/memory envelopes as settled facts

The architecture direction is plausible and likely correct, but those numbers
must be reframed as hypotheses to validate rather than facts to design around.

## Goals

- eliminate hosted story flows that still require filesystem fallback for known
  indexed data
- keep MCP conversational while preserving canonical identity and portable
  references
- enrich repository and workload context with structured deployment, resource,
  and environment facts when the evidence exists
- fix remaining tool-contract gaps that materially block hosted investigations
- add a process-pool parse engine behind a feature flag without breaking the
  current async commit/finalization pipeline
- verify both workstreams through durable integration and docker-backed e2e
  coverage

## Non-Goals

- breaking existing MCP or HTTP consumers to clean up legacy shapes
- changing commit/finalization semantics in the same slice as the new parse
  engine
- treating unverified performance estimates as acceptance criteria
- adding filesystem fallback as a shortcut to make story acceptance tests pass
- merging the two workstreams into one giant implementation task with shared
  risk

## Shared Constraints

### Additive public contract

This slice is additive-only for MCP/API consumers:

- accept plain names where the product already wants conversational ergonomics
- preserve canonical IDs and repo-relative paths in public outputs
- populate currently empty or weak fields rather than renaming or removing them
- add shaping controls instead of replacing existing tool surfaces outright

### Evidence portability

- no hosted acceptance flow may require server-local filesystem access
- no story output may expose local checkout paths as a normal user-facing field
- no new fix may widen raw path or raw Cypher input acceptance

### Correctness before performance

Multiprocess parsing must be treated as an execution-engine swap, not a parsing
semantic rewrite. The graph/content outputs for a repository must remain
equivalent before and after the engine change.

## Workstream A: Hosted Story And Tool Gaps

### Problem statement

The current story surfaces are much better than the original hosted
investigation path, but several gaps still prevent a fully self-contained,
hosted "tell me everything" workflow:

- repository and service context still leave important deployment/resource
  fields empty or under-shaped
- infra search still misses some resource classifications that already exist in
  the graph
- blast-radius answers are thinner than the consumer evidence already available
- deployment-trace responses are filtered better than before but still lack
  first-class shaping controls

### Design

The fix point should be the shared query and enrichment layer, not MCP-only
wrappers.

#### A1. Centralize identifier normalization

Keep all existing repo-name and canonical-ID resolution in shared query helpers.
Do not duplicate resolver logic in individual tools.

This means:

- content and status tools continue using shared resolution helpers
- remaining hosted tools that still assume names or paths directly should be
  normalized through the repository query layer
- HTTP remains canonical-ID based where that is already the public contract

#### A2. Enrich repository context

Extend repository context so it can answer more of the hosted story directly:

- `platforms`
- `environments`
- `deploys_from`
- compact `deployment_chain`
- richer `consumer_repositories`
- better truthfulness notes when finalization is incomplete

The key principle is: if the evidence is already in graph/content enrichment,
`get_repo_context` and `get_repo_story` should expose it instead of forcing
secondary diagnostics.

#### A3. Enrich workload/service context

Extend workload/service context to populate structured deployment/resource
fields when the underlying content already contains the signal:

- `cloud_resources`
- `shared_resources`
- `dependencies`
- `entrypoints`

Likely evidence sources:

- Helm values
- ArgoCD/Kustomize overlays
- Crossplane/XIRSA policy documents
- environment-specific config files

The output must remain explicit about inferred versus directly observed data.

#### A4. Fix infra classification gaps

Bring `find_infra_resources` into alignment with what is already indexed:

- surface `ApplicationSet` under ArgoCD, not only Applications
- surface Crossplane claims under Crossplane when their `apiVersion`/group
  matches known XRD-backed claim patterns
- avoid treating those same resources as only generic K8s hits when a more
  specific classification is available

#### A5. Strengthen blast radius

`find_blast_radius` should stop being a thin graph traversal that ignores
better evidence already computed elsewhere. When direct tier/risk metadata is
missing, it should still return meaningful dependent repositories and clearly
label what is inferred versus unknown.

The design preference is:

- direct graph traversal where it works
- fallback augmentation from repository consumer evidence
- truthful null handling for metadata that is genuinely absent

#### A6. Shape deployment traces

`trace_deployment_chain` should default to a focused direct chain suitable for
interactive hosted use.

Add explicit shaping controls such as:

- `direct_only`
- `max_depth`
- `include_related_module_usage`
- response truncation metadata when large branches are omitted

The contract should distinguish:

- directly relevant deployment chain
- adjacent shared infrastructure/module usage

### Hosted acceptance contract

The following hosted flow should succeed without local filesystem fallback for
known indexed data:

1. repository overview
2. workload/service context
3. repo-relative file content by repo name where MCP allows conversational
   inputs
4. focused deployment trace
5. blast radius with concrete repo identities

When finalization is incomplete, the result must explain the missing coverage
instead of silently returning empty arrays that look authoritative.

## Workstream B: Multiprocess Parse Engine

### Problem statement

The current parse path still uses `asyncio.to_thread(...)` inside
`parse_repository_snapshot_async`, with repo-level concurrency in the
coordinator and optional per-repo file concurrency through
`PCG_REPO_FILE_PARSE_CONCURRENCY`.

That means the current architecture still relies on thread-based execution for
CPU-heavy parsing work. The multiprocess PRD is correct that this is the seam to
change if parse throughput is now the bottleneck.

### Design

Implement a feature-flagged process-pool parse engine that coexists with the
current thread-based engine until correctness and operational behavior are
proven.

#### B1. Keep the coordinator in the main process

Do not rewrite the entire indexing coordinator. The main process still owns
the mutable control plane:

- run-state checkpoints
- bounded queue creation and backpressure
- commit orchestration
- finalization
- coverage publication
- telemetry aggregation

Parse workers should only return serializable repository snapshots. They should
not write graph state, finalize runs, or decide when a run has completed.

#### B2. Model the queue explicitly

The queue shape we are documenting is:

1. repository discovery and run setup
2. worker-side repository parse and snapshot creation
3. bounded queue of parsed snapshots waiting to commit
4. serialized commit of one snapshot at a time
5. finalization and coverage publication

The first slice keeps pre-scan adjacent to parse work inside the worker so the
worker can return a complete snapshot. Pre-scan is not a separate queue stage
yet.

The queue should be bounded by `PCG_INDEX_QUEUE_DEPTH`; worker fanout should be
bounded by `PCG_PARSE_WORKERS`; the per-repository file parse knob can stay
opt-in under `PCG_REPO_FILE_PARSE_CONCURRENCY`.

#### B3. Add process-local parser initialization

Worker processes cannot reuse the live `GraphBuilder` object directly.
Introduce a standalone worker module that:

- initializes parser registries per worker
- receives serializable parse requests
- returns serializable parse results
- hides non-picklable parser/runtime details inside the worker process

#### B4. Gate the engine

Do not remove the current thread path in phase 1.

Introduce a feature flag such as:

- `PCG_PARSE_EXECUTION_ENGINE=thread|process`

and keep the existing file-concurrency knob as a fallback until the process
path is proven. The repo-level parse worker count can continue to exist, but
its meaning must be clearly documented for both engines.

#### B5. Separate measurement from implementation

The first multiprocess slice must add a repeatable measurement harness and
baseline capture rather than encode guessed thresholds into tests.

Acceptance for phase 1 should be:

- correctness equivalence on representative repos
- no deadlocks or orphaned workers
- stable checkpoint/resume behavior
- measured improvement on at least one CPU-heavy corpus
- stable span, metric, and log names for Grafana/Loki correlation

It should not be:

- "must be exactly 3.2x faster"

#### B6. Preserve output equivalence

The process engine must preserve:

- parsed file payload shape
- import maps
- repository snapshot semantics
- error isolation behavior
- downstream commit/finalization behavior

If the process path changes any of those, it is a correctness bug, not a mere
performance regression.

## Interaction Between Workstreams

These workstreams are related operationally but should not block each other at
the code-organization level.

The hosted story work depends on better indexed evidence, but it should still be
designed and tested against the current engine. The multiprocess parsing work
should improve freshness and throughput, not redefine the hosted story
contract.

The coordination rules are:

- story completeness must not assume multiprocessing exists
- multiprocessing acceptance must include query-level regression checks to
  ensure no evidence disappears
- shared fixtures and docker-backed verification should cover both correctness
  and user-facing story quality

## Testing Strategy

### Hosted story gaps

- unit tests for each enrichment and classification fix
- MCP and HTTP integration tests for the hosted diagnostic flow
- docker-backed e2e path that proves the story can be assembled without
  filesystem fallback

### Multiprocess parsing

- unit tests for worker init, worker parse entrypoints, and engine selection
- coordinator/pipeline tests for process-engine scheduling and failure handling
- snapshot equivalence tests comparing thread and process engines on the same
  fixture repo
- benchmark harness that records timing/memory data without asserting fragile
  machine-specific thresholds

### Cross-workstream regression

- story/integration suites must pass under the default engine
- at least one representative integration path should also run with the process
  engine enabled

## Risks And Guardrails

### Hosted story risks

- widening fuzzy-name acceptance too far can create ambiguous or unsafe lookups
- richer evidence can accidentally leak local paths or internal-only details
- over-eager inference can present guesses as facts

Guardrails:

- resolve through canonical graph identity
- keep HTTP canonical where already designed
- preserve explicit `limitations` and `coverage` signals

### Multiprocess parsing risks

- non-picklable parser/runtime objects can break worker execution
- worker crashes or hung pools can strand coordinator progress
- memory growth per worker can make the engine look fast but operationally poor
- platform-specific start-method behavior can differ between local and linux
  deployments

Guardrails:

- isolate worker state behind a dedicated module
- gate the feature
- add explicit crash and timeout handling
- measure before changing defaults

## Acceptance Criteria

This umbrella design is satisfied when:

- hosted MCP/API flows can answer the targeted story questions without
  filesystem fallback for known indexed data
- repository and service context are materially richer and more truthful
- remaining hosted diagnostics expose shaping controls where raw breadth is
  still too noisy
- the multiprocess parse engine exists behind a feature flag
- thread and process engines produce equivalent parse/commit outcomes on
  representative fixtures
- integration and docker-backed e2e coverage become permanent for both
  workstreams

## Implementation Direction

Implementation should proceed as one umbrella effort with two coordinated
workstreams:

- Workstream A first: hosted story/tool gaps
- Workstream B in parallel behind a feature flag: multiprocess parse engine

The umbrella implementation plan should keep these as separate chunks and avoid
forcing one risky, all-or-nothing branch.
