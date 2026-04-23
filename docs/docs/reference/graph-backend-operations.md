# Graph Backend Operations

This page covers day-two operations for the local graph backend sidecar on
the `local_authoritative` profile. For install, see
[Graph Backend Installation](graph-backend-installation.md). For the
lifecycle contract that governs startup / shutdown ordering, see
[Local Host Lifecycle](local-host-lifecycle.md).

## Current command group

```text
pcg graph status
```

`pcg graph status` is wired today. The remaining lifecycle commands
(`pcg graph start|stop|logs|upgrade`) are still planned and currently return
actionable guidance instead of performing real lifecycle control.

The local-authoritative runtime still manages the sidecar automatically when
you run a PCG local host entrypoint such as:

```bash
PCG_QUERY_PROFILE=local_authoritative pcg watch .
```

That path requires a discoverable NornicDB binary. Laptop installs prefer
`nornicdb-headless`; the full `nornicdb` binary is supported only when users
opt in because it is larger. See
[Graph Backend Installation](graph-backend-installation.md).

### `pcg graph status`

Reports, for the current workspace:

- whether a local NornicDB binary was discovered
- binary path
- discovered version
- whether a workspace owner is present
- backend PID
- loopback bind address
- Bolt port
- HTTP health port
- data directory path
- graph log path
- whether the backend currently looks healthy

For the current NornicDB-backed `local_authoritative` path, health means:

- the recorded graph PID is alive
- `GET /health` on the recorded loopback HTTP port succeeds
- the recorded loopback Bolt port accepts TCP connections

The sidecar writes logs under `${PCG_HOME}/local/workspaces/<workspace_id>/logs/graph-nornicdb.log`.

PCG generates a random graph admin password per workspace data root and
persists it under `graph/nornicdb/pcg-credentials.json` with `0600`
permissions. The live owner also copies it to `owner.json` so attach
processes can connect; `pcg graph status` does not print the secret.

## Health probe

`pcg doctor` probes the graph backend as part of the local-host check
suite when the active profile is `local_authoritative`. A failing probe
prints the backend-specific failure (bolt timeout, health failure, version
mismatch, data directory not writable) and returns a non-zero exit code.

## Troubleshooting

### Backend installed but not starting

Check, in order:

1. `pcg graph status` — did PCG discover the expected NornicDB binary?
   If discovery reports not installed, verify the candidate binary prints a
   `NornicDB ...` version string.
2. open `${PCG_HOME}/local/workspaces/<workspace_id>/logs/graph-nornicdb.log`
   — did the backend emit an error?
3. `ls -la ${workspace_root}/graph/` — is the data directory writable by
   the current user?
4. Loopback ports — verify that the recorded Bolt and HTTP ports are still
   free before startup and still bound to the graph PID after startup.

### Backend running but queries return `backend_unavailable`

- The PCG process may be out of sync with `owner.json`. Run
  `pcg graph status`; if the PCG host thinks the backend is absent,
  restart the lightweight host: `pcg watch` will re-read owner state.
- Graph backend may be in recovery. On restart after an unclean
  shutdown, NornicDB runs Badger + MVCC recovery. Wait; tail
  `logs/graph-nornicdb.log`.

### Backend stuck after crash

- Check `owner.json` for `graph_pid`. If that PID is dead but data
  directory locks remain, the graph backend may require manual cleanup.
  Remove stale lock files in the data directory only after confirming no
  live process holds them.
- The lightweight host reclaim flow includes a best-effort internal stop
  before reclaim; see
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
