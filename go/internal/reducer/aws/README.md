# Reducer / AWS

`reducer/aws` records the accepted scaffold for the AWS cloud-resource
reducer family. The package names the projector components and the readiness
checkpoints that future implementations must publish; it is not yet wired
into runtime callers.

## Purpose

Pin the runtime contract (component list, published checkpoints) for AWS
canonical projection so ADRs, fixtures, and future reducer wiring share a
single source of truth.

## Ownership boundary

- Owns: the AWS scaffold contract and its `Validate` shape.
- Does not own: live AWS collection, materialization, or graph writes. None
  of those exist in this package today.

## Exported surface

- `PublishedCheckpoint{Keyspace, Phase}`.
- `RuntimeContract{Components, Checkpoints}` plus `Validate`.
- `DefaultRuntimeContract()` and `RuntimeContractTemplate()` return
  defensive copies of the accepted scaffold.

The scaffold lists four components - `resource_projector`,
`relationship_projector`, `dns_projector`, `image_projector` - and one
checkpoint: `cloud_resource_uid` reaching `canonical_nodes_committed`.

## Dependencies

- `go/internal/reducer` for `GraphProjectionKeyspace` and
  `GraphProjectionPhase` constants.

## Telemetry

None. Scaffold types only; runtime telemetry will be defined when the
projector family is implemented.

## Gotchas / invariants

- This is a scaffold. It does not produce facts, does not enqueue work, and
  does not publish phase rows at runtime. Treat the contract as a planning
  artifact, not as a deployable behavior.
- The single accepted checkpoint targets Phase 1 canonical writes
  (`canonical_nodes_committed`). The package does not yet model the
  post-Phase-3 reopen path described in CLAUDE.md "Facts-First Bootstrap
  Ordering"; downstream domains that consume `resolved_relationships`
  populated from AWS canonical nodes still need the standard reopen
  mechanism, owned outside this package.
- `Validate` enforces non-blank components, keyspaces, and phases, but does
  not check that the listed component names match any concrete
  implementation.

## Related docs

- `docs/docs/architecture.md`
- `go/internal/reducer/dsl/README.md`
- `go/internal/reducer/tfstate/README.md`
