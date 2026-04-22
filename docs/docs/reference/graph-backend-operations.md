# Graph Backend Operations

This page covers day-two operations for the local graph backend sidecar on
the `local_authoritative` profile. For install, see
[Graph Backend Installation](graph-backend-installation.md). For the
lifecycle contract that governs startup / shutdown ordering, see
[Local Host Lifecycle](local-host-lifecycle.md).

## Command group

```text
pcg graph start
pcg graph stop
pcg graph status
pcg graph logs
pcg graph upgrade
```

All commands operate on the graph backend tied to the current workspace.

### `pcg graph start`

Starts the graph backend sidecar under the current workspace data root.
Used internally by the lightweight host startup sequence; safe to invoke
manually for debugging.

- Binds to a Unix socket under `${TMPDIR}/pcg/<workspace_id>/graph.sock`
  (or a shorter runtime directory if `${TMPDIR}` itself is too long for
  `sun_path`).
- Writes the PID, socket path, and data directory into `owner.json`.
- Waits until the backend accepts Bolt connections before returning.

### `pcg graph stop`

Requests graceful shutdown of the graph backend. Equivalent to the step
that runs during lightweight host clean shutdown. Use `--force` to send an
immediate stop after the graceful window expires.

### `pcg graph status`

Reports, for the current workspace:

- whether the graph backend is installed
- whether the graph backend is running
- backend version
- data directory path
- socket path
- last startup time
- last Bolt ping result

Exit code is non-zero when the backend should be running but is not.

### `pcg graph logs`

Tails the graph backend log file under `${workspace_root}/logs/graph.log`.
Respects `--follow`, `--lines`, `--since`.

### `pcg graph upgrade`

Shorthand for:

1. `pcg install nornicdb --version <next>`
2. `pcg graph stop`
3. `pcg graph start`

Fails closed if step 1 does not complete cleanly or if the new backend does
not accept connections after restart.

## Health probe

`pcg doctor` probes the graph backend as part of the local-host check
suite when the active profile is `local_authoritative`. A failing probe
prints the backend-specific failure (bolt timeout, socket missing, version
mismatch, data directory not writable) and returns a non-zero exit code.

## Troubleshooting

### Backend installed but not starting

Check, in order:

1. `pcg graph status` — is the binary where `owner.json` expects it?
2. `pcg graph logs --lines 200` — did the backend emit an error?
3. `ls -la ${workspace_root}/graph/` — is the data directory writable by
   the current user?
4. Socket path length — on macOS, `sun_path` is 104 chars; a deeply
   nested `${TMPDIR}` can exceed that. The runtime should log a fallback
   runtime dir; verify which path it chose.

### Backend running but queries return `backend_unavailable`

- The PCG process may be out of sync with `owner.json`. Run
  `pcg graph status`; if the PCG host thinks the backend is absent,
  restart the lightweight host: `pcg watch` will re-read owner state.
- Graph backend may be in recovery. On restart after an unclean
  shutdown, NornicDB runs Badger + MVCC recovery. Wait; tail
  `pcg graph logs`.

### Backend stuck after crash

- Check `owner.json` for `graph_pid`. If that PID is dead but data
  directory locks remain, the graph backend may require manual cleanup.
  Remove stale lock files in the data directory only after confirming no
  live process holds them.
- The lightweight host reclaim flow includes a best-effort stop
  (`pcg graph stop --force` before reclaim); see
  [Local Host Lifecycle](local-host-lifecycle.md).

## Telemetry

Every query response from the graph backend is labeled with
`graph_backend` (`neo4j` or `nornicdb`) on:

- telemetry spans (`graph_backend` attribute)
- query latency histograms (`graph_backend` label)
- error counters (`graph_backend` label)
- optional `truth.backend` field in responses

## Migration between backends

Switching the active graph backend for a workspace requires:

1. Stop the lightweight host and any running `pcg watch`.
2. Flip `PCG_GRAPH_BACKEND` in the environment.
3. Either:
   - Re-index the workspace with `pcg index <path> --force` so the new
     backend receives fresh canonical writes, or
   - Run migration tooling if available (see the ADR §Migration Path for
     current status).
4. Restart `pcg watch`.

`owner.json` should record the active `graph_backend` so downstream
diagnostics can see which backend owned the last successful run.

## Non-goals

- Running multiple graph backends simultaneously on one workspace. The
  workspace lock admits exactly one owner and exactly one graph backend
  at a time.
- Running the graph backend headless without a PCG owner. The sidecar is
  owned by the lightweight host, not by the user shell.
