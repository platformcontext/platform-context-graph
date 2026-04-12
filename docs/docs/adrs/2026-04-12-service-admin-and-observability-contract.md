# ADR: Service Admin And Observability Contract

**Status:** Accepted

## Context

PCG is moving toward multiple long-running services with different scaling and
failure modes. Operators need every runtime to expose the same basic health and
status story so the platform can be monitored live without learning a different
shape for each service.

Telemetry alone is not enough. We also need a standard admin surface that can
answer "is it alive, is it ready, what is it doing, and where is the backlog"
from both CLI and HTTP consumers.

## Decision

Every long-running PCG service will follow the same admin and observability
contract.

Required runtime surface:

- `GET` and `HEAD` `/healthz`
- `GET` and `HEAD` `/readyz`
- `GET` and `HEAD` `/admin/status`
- `/metrics` when the service exposes metrics

Required operator semantics:

- health indicates the process is alive
- readiness indicates the service can do useful work
- status reports queue, stage, backlog, and failure summary
- status is inspectable through CLI and HTTP with the same underlying report
- OTEL metrics, traces, and structured logs use the same correlation fields
  across services

The exact counters and stage names may differ by service, but the operator
contract does not.

## Why This Choice

- It gives operators one mental model for every runtime.
- It keeps future collectors and reducers from inventing bespoke probes.
- It makes local debugging and deployed debugging look the same.
- It aligns the admin surface with the shared observability contract already
  defined for the rewrite.

## Consequences

Positive:

- Services are easier to inspect and automate against.
- Readiness and backlog state are visible without spelunking logs.
- Future services can be added without designing a new admin shape.

Tradeoffs:

- Every service must implement the shared contract before it is considered
  complete.
- Service-specific instrumentation still needs to be mapped into the shared
  report shape.

## Implementation Guidance

- Reuse the shared status reader and admin HTTP adapter wherever possible.
- Treat missing health, readiness, or status endpoints as a release blocker.
- Keep the CLI and HTTP admin views backed by the same report model.
- Document any service-specific extension in the service docs, not by changing
  the core contract.
