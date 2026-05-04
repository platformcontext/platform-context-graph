# PCG Local

## Purpose

Local-host filesystem contract for the lightweight code-intelligence runtime.
Resolves the `${PCG_HOME}/local/workspaces/<id>/` layout, owns the
`owner.lock` flock protocol, and manages embedded Postgres lifecycle on Unix.

## Ownership boundary

See `doc.go` for the canonical contract paragraph; the spec lives in
`docs/docs/reference/local-data-root-spec.md` and
`docs/docs/reference/local-host-lifecycle.md`. This package never touches
the durable graph or shared work queue — it only manages a single user's
local workspace.

## Exported surface

- `Layout`, `ResolveHomeDir`, `ResolveWorkspaceRoot`, `WorkspaceID`,
  `BuildLayout` for layout resolution.
- `OwnerLock`, `AcquireOwnerLock`, `ErrWorkspaceOwned` for the flock
  protocol (Unix); a Windows shim returns `ErrWorkspaceOwned`.
- `OwnerRecord`, `ReadOwnerRecord`, `WriteOwnerRecord`.
- `EnsureLayoutVersion`, `ReadLayoutVersion`, `WriteLayoutVersion`,
  `ErrIncompatibleLayoutVersion`.
- `StartupDeps`, `PrepareWorkspace`.
- `ReclaimDeps`, `ValidateOrReclaimOwner`, `DefaultReclaimDeps`.
- `ProcessAlive`, `SocketHealthy`, `StopEmbeddedPostgres` health helpers.
- `ManagedPostgres`, `StartEmbeddedPostgres`, `PostgresDSN`,
  `LocalQueryProfile` for the embedded Postgres lifecycle (Unix only;
  Windows returns errors).

## Dependencies

Standard library only. Postgres lifecycle uses platform-specific files
(`*_unix.go`, `*_windows.go`) gated by build tags.

## Telemetry

None.

## Gotchas / invariants

- Workspace ID is derived from the absolute, symlink-resolved
  `WorkspaceRoot`. Two checkouts at different paths get different IDs.
- `ErrWorkspaceOwned` means another live process holds the flock.
  `ValidateOrReclaimOwner` is the recovery path when the prior owner died
  without releasing.
- The Windows owner-lock and embedded Postgres surfaces are intentionally
  stubs that fail loudly. The lightweight local runtime is Unix-only.
- Layout version is the `local-data-root-spec` version. Bumping it without
  a documented migration breaks existing workspaces.

## Related docs

- `docs/docs/reference/local-data-root-spec.md`
- `docs/docs/reference/local-host-lifecycle.md`
- `docs/docs/reference/local-testing.md`
