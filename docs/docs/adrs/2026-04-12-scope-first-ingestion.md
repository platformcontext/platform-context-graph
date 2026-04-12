# ADR: Scope-First Ingestion

**Status:** Accepted

## Context

PCG is moving beyond repository indexing. The next wave of collectors includes
AWS, Kubernetes, ETL systems, and other infrastructure sources that are not
meaningfully represented by a repository alone. A repository-centric work model
cannot describe cloud inventory shards, cluster slices, stack state, or other
bounded operational scopes without forcing those systems into a Git-shaped
model they do not naturally fit.

The storage and queue layers therefore need a first-class durable object that
represents "what was observed" and "what should be refreshed" independent of
the source family.

## Decision

PCG will use a **scope-first ingestion model**.

The durable units of ingestion will be:

- `ingestion_scopes`
- `scope_generations`

Facts, work items, replay records, and projection outputs will reference scope
identity instead of treating `repository_id` as the primary key for every
collector.

`repository_id` remains valid metadata for repo-backed sources, but it is no
longer the universal identity model for the platform.

## Scope Model

`ingestion_scopes` represent the bounded thing a collector owns. A scope should
describe:

- `source_system` such as `git`, `aws`, `kubernetes`, `terraform-state`, or
  `cloudformation`
- `scope_kind` such as `repository`, `aws-service-shard`, `cluster`,
  `stack`, or `state-object`
- `scope_id` as the stable durable identifier
- `parent_scope_id` when a scope is nested inside a larger boundary
- `collector_kind` or equivalent ownership metadata
- partitioning and refresh metadata needed for scheduling

`scope_generations` represent the authoritative version of a scope at a point
in time. A generation captures the snapshot that the collector produced and the
projection engine should trust until a later generation replaces it.

## Why Scope First

- It removes repository bias from the ingestion substrate.
- It supports Git, cloud, and data collectors with one durable contract.
- It makes scheduling, replay, and backfill easier to reason about.
- It gives the system a clean place to record freshness, ownership, and
  hierarchy.
- It prevents collector-specific schema forks from appearing later.

## Why Generations Are Authoritative Snapshots By Default

PCG needs correctness first. A generation is the source of truth for the scope
it represents.

That means:

- the latest successful generation replaces the prior truth for that scope
- deletes and absences are meaningful because they are visible at the generation
  boundary
- backfill and replay can recreate the same scope state deterministically
- drift detection becomes possible because a later generation can be compared
  against the prior one

Event-driven updates may trigger work faster, but they do not replace the
generation model. Events are accelerators. Generations are the durable truth.

## Consequences

Positive:

- One ingestion contract for every future collector.
- Cleaner support for AWS, Kubernetes, ETL, and state-based sources.
- Better freshness and replay semantics.
- Better operational visibility into ownership, stale work, and backfills.
- A durable foundation for reducer scheduling and canonical graph updates.

Tradeoffs:

- The storage and work-queue schemas need real refactoring.
- Existing repository-focused paths must be migrated carefully.
- Some query and admin code will need to stop assuming that repository is the
  primary unit of work.

## Implementation Guidance

- Create `ingestion_scopes` as the long-lived owner record.
- Create `scope_generations` as the durable snapshot history for each scope.
- Key work items and replay metadata by `scope_id` and `generation_id`.
- Keep repository identity as an association, not as the universal storage key.
- Use the scope/generation boundary to drive projection and reconciliation.
- Do not build new collectors on top of repository-only queue semantics.
