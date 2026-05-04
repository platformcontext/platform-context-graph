# Relationships

`relationships` extracts Terraform, Helm, Kustomize, Argo CD, and related
deployment evidence before reducer admission.

This package should describe evidence, not invent deployment truth. Ambiguous
signals must stay ambiguous until a stronger contract admits them.

## Dependencies

Internal packages: `internal/facts`, `internal/terraformschema`. Reducer
admission lives in `internal/reducer`; this package supplies evidence
inputs only.

## Telemetry

Inherits from `internal/telemetry`; this package does not emit its own
metrics or spans. Extraction outcomes are surfaced by the reducer when
admitted, and by `internal/storage/postgres` when persisted as evidence
rows.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/local-testing.md`
