# Buildinfo

## Purpose

Single source for the application version string reported by the API, MCP
server, ingester, reducer, and admin surfaces.

## Ownership boundary

Owns the `Version` `var` and `AppVersion()` accessor. Nothing else may keep its
own version constant.

## Exported surface

- `Version` — package var overridden at build time via
  `-ldflags="-X github.com/.../internal/buildinfo.Version=<value>"`.
- `AppVersion() string` — trims whitespace and falls back to `"dev"` when the
  injected value is empty.

## Dependencies

Standard library only.

## Telemetry

None directly. Callers report the version into their own logs, metrics, and
status payloads.

## Gotchas / invariants

- `Version` must only ever be written via `-ldflags`; nothing in code should
  reassign it.
- An empty or whitespace-only override collapses to `"dev"`. Treat `"dev"` as
  "non-release source build" in operator dashboards.

## Related docs

- `docs/docs/reference/local-testing.md`
- `Dockerfile` (release builds inject the value)
