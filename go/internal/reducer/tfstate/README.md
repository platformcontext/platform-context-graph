# Reducer / Terraform State

`reducer/tfstate` records the accepted scaffold for the Terraform
state-derived reducer family. The package names the projector components
and readiness checkpoints; it is not yet wired into runtime callers.

## Purpose

Pin the runtime contract (component list, published checkpoints) for
Terraform state canonical projection so ADRs, fixtures, and future reducer
wiring share a single source of truth.

## Ownership boundary

- Owns: the Terraform state scaffold contract and its `Validate` shape.
- Does not own: live Terraform state collection, materialization, or graph
  writes. None of those exist in this package today.

## Exported surface

- `PublishedCheckpoint{Keyspace, Phase}`.
- `RuntimeContract{Components, Checkpoints}` plus `Validate`.
- `DefaultRuntimeContract()` and `RuntimeContractTemplate()` return
  defensive copies of the accepted scaffold.

The scaffold lists three components - `resource_projector`,
`module_projector`, `output_projector` - and two checkpoints:
`terraform_resource_uid` and `terraform_module_uid`, both at
`canonical_nodes_committed`.

## Dependencies

- `go/internal/reducer` for `GraphProjectionKeyspace` and
  `GraphProjectionPhase` constants.

## Telemetry

None. Scaffold types only; runtime telemetry will be defined when the
projector family is implemented.

## Gotchas / invariants

- This is a scaffold. It does not produce facts, does not enqueue work, and
  does not publish phase rows at runtime.
- Both accepted checkpoints are Phase 1 (`canonical_nodes_committed`)
  publications. Downstream domains that consume `resolved_relationships`
  derived from Terraform state canonical rows still need the post-Phase-3
  reopen mechanism described in CLAUDE.md "Facts-First Bootstrap Ordering"
  to re-trigger after backfill; that reopen lives outside this package.
- `Validate` enforces non-blank components, keyspaces, and phases; it does
  not check that listed component names map to any concrete implementation.

## Related docs

- `docs/docs/architecture.md`
- `go/internal/reducer/aws/README.md`
- `go/internal/reducer/dsl/README.md`
