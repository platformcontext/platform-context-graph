# App

## Purpose

`internal/app` is the thin shell every PCG binary uses to load runtime config,
build lifecycle hooks, and run a `Runner`. It keeps `cmd/*/main.go` short and
uniform across the API, MCP server, ingester, reducer, and bootstrap-index.

## Ownership boundary

Owns the hosted-application contract: `Application`, `Lifecycle`, `Runner`,
lifecycle composition, and the optional status-server attachment. Backing config,
admin handlers, and metrics endpoints live in `internal/runtime` and are wired
in here, not redefined.

## Exported surface

- `Application` — config, observability, lifecycle, runner.
- `Lifecycle` interface and `ComposeLifecycles` for ordered start with rollback
  on partial failure.
- `Runner` interface for the long-running body of a service.
- `New`, `NewHosted`, `NewHostedWithStatusServer` constructors.
- `MountStatusServer` for attaching the shared admin and metrics listeners.

## Dependencies

- `internal/runtime` for `Config`, `Observability`, `Lifecycle`, the status
  admin server, and the optional metrics server.
- `internal/status` for the `Reader` consumed by the status admin surface.

## Telemetry

No metrics, traces, or structured logs are emitted from this package. Telemetry
is owned by the runtime and status servers it composes in.

## Gotchas / invariants

- `Application.Run` requires both `Lifecycle` and `Runner`; either being nil
  is a startup error.
- `ComposeLifecycles` rolls back already-started parts on first error so half-
  started processes do not leak resources.
- `MountStatusServer` only adds a separate metrics listener when
  `Config.MetricsAddr` is set and differs from `Config.ListenAddr`.

## Related docs

- `docs/docs/deployment/service-runtimes.md`
- `go/internal/runtime/README.md`
