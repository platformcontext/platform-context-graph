# ADR: Resiliency And Concurrency Contract

**Status:** Accepted

## Context

PCG is moving from a repository-centered write path into a multi-service data
plane that will soon support Git, AWS, Kubernetes, ETL, and other collectors.

That shift creates two failure modes if the concurrency model is left vague:

1. future workers will overuse in-memory concurrency primitives and accidentally
   turn service boundaries into implicit, lossy pipelines
2. the platform will scale unevenly because CPU-bound work, I/O-bound work,
   retries, and backpressure will not be designed as one contract

The rewrite also needs a durable answer to a recurring design question:

- when should the platform use Go channels and worker pools
- when should it use durable queues and leases instead

## Decision

PCG will treat resiliency and concurrency as a first-class architecture
contract.

The platform will use two different concurrency layers on purpose:

- **in-process concurrency** for bounded parallel work inside one service
- **durable queue boundaries** for work that crosses service, source, or
  canonical-truth ownership boundaries

These layers are complementary, not interchangeable.

## In-Process Concurrency Rules

Inside one Go service:

- use bounded worker pools rather than unbounded goroutine fan-out
- use channels when they clarify producer/worker/result coordination,
  cancellation, or backpressure inside that one process
- prefer explicit worker-count and queue-capacity settings over implicit
  concurrency
- size CPU-bound work from available processors and service tuning, not from
  request count
- keep I/O-bound concurrency bounded separately from CPU-bound concurrency

Examples:

- parser workers may use bounded channel-fed worker pools
- repository discovery may use bounded fan-out for remote calls
- projector or reducer internals may use bounded per-batch parallelism when the
  write contract remains deterministic

Non-rule:

- channels are not the default answer for every problem
- if a concurrency boundary needs replay, recovery, leasing, or cross-service
  visibility, it is not a channel problem anymore

## Durable Boundary Rules

Use durable queues, leases, and idempotent writes when work crosses one of
these boundaries:

- collector to projector
- projector to reducer
- source-local truth to canonical truth
- one runtime process to another
- one retry domain to another

Durable boundaries must provide:

- stable identity for the work unit
- bounded retries with classified failure reasons
- replay and dead-letter visibility
- operator-visible backlog and age
- idempotent reprocessing behavior

## Resiliency Rules

Every long-running service must be resilient to:

- partial source outages
- partial database outages
- stale leases
- duplicate delivery
- slow consumers
- hot partitions
- partial success inside one batch

The design contract is:

- no stage should require a full platform re-index to recover one failed work
  unit
- every stage should process bounded units such as scope generations or reducer
  intents
- canonical writes must be idempotent at the work-unit boundary
- retries must be classified and observable
- backpressure must slow producers before it corrupts the system

## Performance Rules

Performance work must preserve correctness and explainability.

Required rules:

- scale by partitioned work, not by enlarging one procedural runtime
- keep collector, projector, and reducer scaling decisions independent
- expose configurable worker counts, channel capacities, lease durations,
  database pools, and batch sizes through env or config
- use database connection pooling as a required service capability, not an
  optional optimization
- prefer multi-core worker pools for CPU-bound parsing and normalization work
- prefer bounded claim-and-drain loops for projector and reducer runtimes

## Why This Choice

- It lets PCG use Go's concurrency model where it is strongest without turning
  durable platform behavior into invisible in-memory state.
- It preserves replay, auditing, and operator visibility as more collectors
  arrive.
- It keeps the platform ready for large AWS, Kubernetes, and ETL inventories
  where one oversized in-memory pipeline would become fragile.

## Consequences

Positive:

- service internals can use channels and worker pools aggressively where
  appropriate
- cross-service behavior stays replayable and observable
- multi-processor machines can be used effectively without giving up bounded
  work ownership
- performance tuning becomes a documented part of the contract

Tradeoffs:

- some boundaries that look simpler with channels must stay durable instead
- worker-pool sizing and backpressure behavior need explicit documentation and
  validation

## Implementation Guidance

- Document every new runtime's concurrency shape in operational terms.
- Keep service-local worker pools bounded and configurable.
- Treat missing backpressure strategy as a design bug.
- Treat missing retry classification as a resiliency bug.
- Prefer one obvious bounded work unit per service role.
- Do not let source-specific parsing logic bypass the durable collector to
  projector to reducer flow.

## End-To-End Mapping Requirement

Every major data-plane flow change must update an end-to-end traversal map that
answers:

- what the work unit is
- which service owns each stage
- whether the handoff is in-memory or durable
- what can be retried at that stage
- which metrics, spans, and status counters prove health at that stage

That mapping must live in the repo docs, not only in chat or PR comments.
