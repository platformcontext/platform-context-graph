# Commands

Each subdirectory builds one PCG executable.

The public CLI command is `pcg`. The service binaries use PCG-prefixed names
when installed for local runtime work, such as `pcg-api`, `pcg-mcp-server`,
`pcg-ingester`, and `pcg-reducer`. Use `scripts/install-local-binaries.sh` from
the repository root when you need that exact binary set on `PATH`.

## Dependencies

Each `cmd/` subdirectory wires together internal packages into a binary;
see the per-binary `main.go` for the exact set. Shared process wiring
lives in `internal/runtime`.

## Telemetry

Process-level telemetry bootstrap (service namespace, OTEL exporter, log
sinks) is configured by `internal/runtime` and `internal/telemetry`. Each
binary inherits that contract; packages do not register their own meter
providers.

## Related docs

- `docs/docs/deployment/service-runtimes.md`
- `docs/docs/reference/cli-reference.md`
- `docs/docs/reference/local-testing.md`
