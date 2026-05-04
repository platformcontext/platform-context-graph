# Facts

`facts` defines the durable records PCG writes before graph projection. These
types are the contract between collection, parsing, queueing, projection, and
reducer-owned materialization.

Avoid convenience fields that only help one caller. A fact should describe source
truth clearly enough for retries, repair, and replay.

## Dependencies

No internal package imports. `internal/facts` is a leaf contract package; it
defines the durable types that collection, projector, reducer, and
`internal/storage/postgres` consume.

## Telemetry

Inherits from `internal/telemetry`; this package does not emit its own
metrics or spans.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/telemetry/index.md`
