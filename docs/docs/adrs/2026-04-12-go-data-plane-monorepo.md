# ADR: Go Data Plane in a Monorepo

**Status:** Accepted

## Context

PCG is becoming a multi-collector platform. Git, SQL, cloud, Kubernetes, ETL,
and CI/CD all need to feed the same knowledge base, but they do not share the
same operational shape. Git indexing is workspace-heavy and snapshot-based.
AWS and Kubernetes collectors will be credentialed, partitioned, and
continuously refreshed. Data-plane orchestration must therefore scale by source
family without forcing one procedural ingest path to carry every concern.

The rewrite began while the repository still contained Python write-side seams
and runtime bridges. Those seams have now been removed from normal platform
operation. The remaining branch work is feature-for-feature parity closure
inside the Go-owned platform, not continued mixed-runtime migration.

## Decision

PCG will remain a **single monorepo** with **multiple deployable services**.
The rewrite will move the write-side data plane to **Go** and define all
cross-service contracts with **Protobuf generated through Buf**.

The monorepo is the right boundary now because it lets us evolve the contracts,
services, fixtures, docs, and validation together. The runtime is still a
multi-service architecture: collectors, resolution, reducers, API, and MCP are
separate processes with separate ownership. The Git repository should not be
the unit of architecture; the runtime service boundary should be.

The write-side data plane must be Go-first because the platform is turning into
a long-running distributed system. Go gives us stronger static contracts,
predictable concurrency, clearer nil handling, and a smaller gap between local
tests and production behavior than the current dynamic write path.

Buf-backed Protobuf contracts are required so that scopes, generations, facts,
work items, reducer intents, and projection results are versioned, documented,
and safe to share across services. Hand-written structs alone are not enough
once collectors and reducers begin to evolve independently.

## Why This Choice

### Why monorepo over multi-repo now

- It keeps the rewrite atomic across code, contracts, docs, fixtures, and tests.
- It avoids version skew while the platform is still defining its stable data
  plane.
- It supports a single release train while the architecture is in motion.
- It keeps local end-to-end validation practical for a long-lived rewrite
  branch.
- It reduces coordination overhead while we are still proving the new model.

### Why multi-service runtime inside the monorepo

- Collectors have different operational needs and should not share one giant
  ingester process.
- Resolution, reducers, API, and MCP each have separate scaling and failure
  modes.
- The repo boundary should not hide the fact that the runtime is already
  service-shaped.
- This makes it easier to introduce AWS, Kubernetes, and future collectors
  without reworking the whole system again.

### Why Go on the write side

- The data plane is a distributed systems problem, not just a parsing problem.
- Strong typing matters for scopes, generations, queue items, reducer intents,
  telemetry payloads, and nil-sensitive state transitions.
- Go gives us better production fit for long-running services than Python for
  this part of the platform.
- The team needs fewer runtime surprises in the part of the system that owns
  correctness, freshness, and persistence.

### Why Protobuf plus Buf

- The platform now needs versioned contracts, not just internal structs.
- Generated code keeps collector and reducer interfaces synchronized.
- Schema evolution becomes explicit and reviewable.
- Cross-language clients stay practical if the read plane or integrations
  remain mixed during the migration.

### Why canonical-first query and MCP stays the default

- PCG is becoming a knowledge base, not a debug dump.
- The default query contract should answer the best resolved question first.
- Source-local or raw evidence views remain available, but only when requested.
- This keeps MCP useful for operators, engineers, and downstream agents without
  forcing them to navigate internal pipeline state by default.

## Consequences

Positive:

- One coherent platform contract for all collectors.
- Easier cross-service evolution.
- Better local and cloud validation story.
- Clearer path to enterprise-grade scale and reliability.
- Less risk of collector-specific data-plane drift.

Tradeoffs:

- The rewrite scope is larger up front.
- The monorepo must stay disciplined so shared code does not become shared
  ambiguity.
- The team must keep contracts strict and versioned, or Go structs alone will
  not deliver the safety we want.

## Implementation Guidance

- Keep the monorepo as the source of truth for contracts, docs, fixtures, and
  service code.
- Introduce Go services for collectors, resolution, reducers, and the API
  surface as separate deployables.
- Define a Buf module for versioned contracts before adding more collectors.
- Prefer explicit package boundaries over hidden shared helpers.
- Treat any historical Python write path as migration history, not as a current
  architecture option.
- Preserve canonical-first query behavior in the public surfaces while exposing
  evidence and raw views as explicit modes.
