# Internal Packages

Internal packages own PCG runtime behavior behind the command binaries. Keep
package boundaries narrow and document the contract at the package or exported
identifier where another package depends on it.

New packages need a package comment, preferably in `doc.go`. Existing packages
should gain package docs when they are touched for behavior, public contracts,
or operator-facing runtime work.

## Dependencies

This directory has no Go source of its own; package-level dependencies are
documented in each child `README.md` and `doc.go`.

## Telemetry

The OTEL contract for every internal package lives in
`internal/telemetry`. Packages that do not emit their own metrics or spans
inherit it through the callers that do.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/telemetry/index.md`
