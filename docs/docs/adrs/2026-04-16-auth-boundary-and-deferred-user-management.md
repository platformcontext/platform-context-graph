# ADR: Auth Boundary And Deferred User Management

**Status:** Accepted

## Context

PlatformContextGraph now runs as a Go-owned split runtime with API, ingester,
resolution, and bootstrap surfaces. During migration proof work we hit the
question of how the platform should authenticate requests in local compose,
operator workflows, and future hosted deployments.

The immediate options are:

1. build a separate authentication or gateway service now
2. keep authentication inside the API boundary for the current platform shape
3. design user management, sessions, or OAuth flows as part of the migration

The current branch goal is still parity-preserving Python-to-Go runtime
conversion, not full identity-platform design. We do not yet have a
multi-tenant control plane, customer-facing login surface, or external product
requirement that justifies a dedicated auth service during this cutover.

## Decision

PCG keeps authentication at the API boundary for now and explicitly defers
user management and OAuth design.

That means:

- the API and MCP runtimes remain the request-authentication boundary for the
  current platform
- the platform may continue to use environment- or deployment-supplied bearer
  tokens for operator and local-runtime scenarios
- the migration does not introduce a separate auth service or gateway-only
  auth dependency as part of the Go cutover
- the migration does not attempt to invent users, tenants, sessions, or OAuth
  flows before the product and deployment model require them

## Why This Choice

- A separate auth service would add another runtime boundary, operational
  surface, and deployment dependency while the current branch is still focused
  on closing runtime and parser parity.
- We do not yet have the product requirements needed to choose between
  service-issued tokens, OIDC, reverse-proxy auth, machine identities, or
  first-party user management.
- Keeping auth in the API boundary preserves a simple operational model for
  local compose, CLI-driven workflows, and internal operator deployments.
- Deferring identity design avoids baking in a migration-era auth shape that
  we would likely replace once hosted or multi-tenant requirements become real.

## Consequences

Positive:

- the Go migration stays focused on runtime ownership and parity work
- the authentication boundary remains understandable: callers authenticate to
  the API or MCP surface, not to a new sidecar platform
- we keep room to adopt a more appropriate future model such as reverse-proxy
  OIDC, service-to-service identity, or first-party user management

Tradeoffs:

- current local and operator auth remains intentionally simple rather than
  fully productized
- some local-proof helpers may need short-term cleanup if they still assume an
  older auto-generated token contract
- future hosted deployment work must reopen this decision with concrete
  product and platform requirements

## Implementation Guidance

- do not create a standalone auth service as part of the Go migration
- keep request authentication logic owned by the API-facing boundary
- treat bearer-token handling as an operator or deployment contract, not as a
  user-management system
- document any local-compose auth assumptions explicitly instead of implying
  that user management already exists
- reopen this ADR when one of these becomes true:
  - external users need sign-in
  - multi-tenant authorization rules are required
  - an ingress or platform gateway becomes the mandated auth boundary
  - hosted deployments need OIDC or delegated enterprise identity

## Follow-Up

Track the revisit as backlog work instead of expanding the migration scope.
The linked implementation issue should cover:

- current auth behavior in local and deployed runtimes
- desired future auth modes
- the decision criteria for keeping auth in-process vs moving it to a gateway
- any eventual OAuth, OIDC, or user-management requirements
