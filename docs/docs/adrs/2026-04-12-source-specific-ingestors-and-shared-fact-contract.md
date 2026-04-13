# ADR: Source-Specific Ingestors And Shared Fact Contract

**Status:** Accepted

## Context

PCG is becoming a multi-collector platform. Git, SQL, AWS, Kubernetes, ETL,
and CI/CD do not share the same discovery model, identity rules, freshness
expectations, or failure modes. A single generic ingester would blur those
differences and eventually turn into a procedural bottleneck.

At the same time, collectors still need a shared handoff into the rest of the
platform. If each source family invents its own fact shape, reducers and query
surfaces will inherit collector-specific drift.

## Decision

PCG will use **source-specific ingestor services** with a **shared fact
contract**.

Rules:

- each collector service owns one source family or a tightly related family of
  source families
- each service is responsible for discovery, normalization, and emission for
  the source it owns
- all collectors emit into the same durable scope, generation, and fact
  contract
- collectors do not write canonical cross-source truth directly
- source-specific runtime behavior lives in the collector boundary, not in one
  mega-ingester

The shared fact contract is the stable bridge between collectors and the rest
of the platform. It is what lets reducers, query surfaces, replay tooling, and
observability stay consistent as new collectors land.

## Why This Choice

- It lets Git, AWS, Kubernetes, SQL, and ETL collectors scale independently.
- It keeps source-specific authentication, polling, and snapshot logic isolated.
- It prevents shared contracts from being redefined by every new collector.
- It gives the platform a single downstream shape even when sources differ.

## Consequences

Positive:

- Collectors can evolve at their own pace.
- New source families can be added without rewriting the whole pipeline.
- Shared reducers and query surfaces stay simpler because the handoff shape is
  stable.

Tradeoffs:

- The service count goes up.
- Each collector must translate its own source semantics into the shared
  contract instead of relying on a generic ingest core.
- Contract versioning becomes mandatory.

## Implementation Guidance

- Keep collector ownership explicit in runtime and package boundaries.
- Version the shared fact contract before adding more collector families.
- Prefer a new source-specific collector over a source-agnostic feature flag
  when the operational shape is meaningfully different.
- Preserve source-local evidence alongside the shared facts so reducers can
  explain how a result was derived.
