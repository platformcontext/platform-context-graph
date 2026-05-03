# Go Runtime

The Go module owns the PCG runtime: CLI, API, MCP server, ingester, reducer,
workflow coordinator, local owner mode, storage adapters, parser support, and
query surfaces.

Use `go test ./...` for broad package validation and `golangci-lint run ./...`
before merging Go changes. The root README and local runbooks show the install
paths for users; this directory is for maintainers working on the runtime.
