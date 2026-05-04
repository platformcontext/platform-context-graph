# Go Runtime

The Go module owns the PCG runtime: CLI, API, MCP server, ingester, reducer,
workflow coordinator, local owner mode, storage adapters, parser support, and
query surfaces.

Use `go test ./...` for broad package validation and `golangci-lint run ./...`
before merging Go changes. The root README and local runbooks show the install
paths for users; this directory is for maintainers working on the runtime.

## Dependencies

This is the Go module root, not a Go package. Internal package boundaries
are documented under `go/internal/*/README.md` and `go/internal/*/doc.go`.

## Telemetry

The runtime telemetry contract is owned by `internal/telemetry`. All
runtime-affecting packages route metrics, spans, and structured logs
through that contract.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/deployment/service-runtimes.md`
- `docs/docs/reference/local-testing.md`
