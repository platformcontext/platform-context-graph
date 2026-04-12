# ADR: Observability Contract

**Status:** Accepted

## Context

Accuracy, performance, stability, scalability, telemetry, tracing, and logging
are top rewrite priorities. That means observability cannot be bolted on after
the data plane is implemented. It must be part of the contract.

The future system will run multiple long-lived services and reducers. Without a
shared observability contract, failures will be visible only as symptoms and
future workers will add ad hoc metrics, traces, and logs that do not line up.

## Decision

The Go data plane will treat telemetry, tracing, and structured logging as a
versioned operational contract.

Every write-path action must expose:

- `scope_id`
- `scope_kind`
- `source_system`
- `generation_id`
- `collector_kind`
- `domain`
- `partition_key`
- correlation or request identifier
- failure classification when relevant

Required data-plane spans are:

- `collector.observe`
- `scope.assign`
- `fact.emit`
- `projector.run`
- `reducer_intent.enqueue`
- `reducer.run`
- `canonical.write`

Required metric families are:

- queue depth and oldest age
- claim latency
- projection latency
- reducer latency
- retry count
- dead-letter count
- stale-generation count
- pending intents by domain

## Why This Choice

- It makes the platform operable under real load.
- It keeps local validation and cloud diagnosis aligned.
- It prevents each new service from inventing its own partial telemetry story.
- It makes cross-service debugging possible for both humans and MCP consumers.

## Consequences

Positive:

- Failures can be diagnosed without code archaeology.
- Performance tuning can be driven by comparable signals across services.
- Future collectors inherit an expected observability surface.

Tradeoffs:

- Instrumentation work is mandatory, not optional.
- Contract drift must be reviewed the same way schema drift is reviewed.

## Implementation Guidance

- Treat missing scope or generation context in telemetry as a bug.
- Keep metric and span names stable once the first contract freeze happens.
- Require structured logs for every terminal failure and every retryable failure
  classification.
- Document any observability contract change alongside the relevant milestone
  plan and versioned contract note.
