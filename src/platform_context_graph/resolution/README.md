# Resolution Package

Canonical projection and post-index resolution logic lives here.

This package currently owns:

- `orchestration/` for the Resolution Engine claim/process loop
- `decisions/` for persisted projection decisions and bounded evidence
- `projection/` for repository, file, entity, relationship, workload, and platform projection from stored facts
- workload materialization helpers
- platform inference and platform family helpers

As PCG evolves, this package should continue absorbing shared identity,
matching, and resolution logic that does not belong to one collector or one
query surface.

For the current Git facts-first path, this package is the runtime owner of
canonical graph writes. Collectors emit facts; resolution projects graph truth.

That applies in two places:

- the standalone `resolution-engine` service role
- the facts-first coordinator cutover path used during Git indexing runs

Both paths use the same projection contracts so the collector no longer owns
final repository/file/entity/relationship/workload/platform graph state.

Observability expectations for this package:

- one work-item span for each projection attempt
- child spans for fact load, fact projection, relationship projection, workload projection, and platform projection
- work-item success/failure counters and duration histograms
- fact-load counters and stage-duration histograms for tuning and backlog triage
- persisted decision counts, evidence counts, and confidence-band metrics for explainability
- retry-age and dead-letter telemetry so exhausted work is visible to on-call responders
- independent queue sampling so backlog and pool saturation remain visible even during idle periods
- structured work-item, decision, and stage-failure logs so on-call can trace completion, retry, dead-letter, replay, and confidence decisions without relying on metrics alone
