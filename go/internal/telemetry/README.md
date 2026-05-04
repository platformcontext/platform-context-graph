# Telemetry

`telemetry` owns PCG's OpenTelemetry contract, metric instruments, span names,
structured log keys, and shared runtime attributes.

Runtime changes should make operator diagnosis easier. Metrics need bounded
labels, traces need useful span names, and logs should carry enough context to
debug a stalled indexing run.

## Dependencies

No internal package imports. `internal/telemetry` is a leaf contract
package consumed by every runtime-affecting package; reverse dependencies
must not be introduced.

## Telemetry

Owns the contract itself. Metric names use the `pcg_dp_` prefix and are
defined in `instruments.go` (for example `pcg_dp_canonical_writes_total`,
`pcg_dp_canonical_phase_duration_seconds`,
`pcg_dp_collector_observe_duration_seconds`,
`pcg_dp_content_rereads_total`). Span names, phase, scope, log key, and
failure-class names are frozen in `contract.go` and must be added there
before use.

## Related docs

- `docs/docs/reference/telemetry/index.md`
- `docs/docs/architecture.md`
