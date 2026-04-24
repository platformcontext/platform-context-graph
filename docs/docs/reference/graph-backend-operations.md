# Graph Backend Operations

This page covers day-two operations for the local graph backend sidecar on
the `local_authoritative` profile. For install, see
[Graph Backend Installation](graph-backend-installation.md). For the
lifecycle contract that governs startup / shutdown ordering, see
[Local Host Lifecycle](local-host-lifecycle.md).

## Current command group

```text
pcg graph status
pcg graph logs
pcg graph stop
pcg graph start
pcg graph upgrade
```

`pcg graph status`, `pcg graph logs`, `pcg graph stop`, and
`pcg graph start` are wired today. `pcg graph upgrade --from <source>` is also
wired for explicit-source replacement of the managed binary from a local
binary path, local tar archive, macOS package, or URL. Bare install now uses
the pinned embedded release manifest when the host platform is covered.
Signature verification remains planned.

`pcg graph stop` is owner-aware. If a healthy local host owns the workspace,
the command signals that owner process so shutdown follows the documented
order: child runtimes stop first, then the graph sidecar, then embedded
Postgres. It only stops the recorded graph process directly when the owner is
already dead and the graph backend is stale.

`pcg graph start` is intentionally foreground. It execs the same local-host
supervisor used by `PCG_QUERY_PROFILE=local_authoritative pcg watch .` and
does not create a detached daemon. Use Ctrl-C to stop it from the same terminal
or `pcg graph stop` from another terminal.

`pcg graph upgrade` refuses to replace the managed binary while the workspace
owner or graph sidecar is still healthy. Stop the workspace first:

```bash
pcg graph stop
pcg graph upgrade --from /absolute/path/to/nornicdb-headless
pcg graph upgrade --from https://example.com/releases/nornicdb-headless-darwin-arm64.tar.gz --sha256 <expected-sha256>
```

The local-authoritative runtime still manages the sidecar automatically when
you run a PCG local host entrypoint such as:

```bash
PCG_QUERY_PROFILE=local_authoritative pcg watch .
```

That path requires a discoverable NornicDB binary. Laptop installs prefer the
managed `${PCG_HOME}/bin/nornicdb-headless` binary created by
`pcg install nornicdb --from <source>`; the full `nornicdb` binary is supported
only when users opt in because it is larger. See
[Graph Backend Installation](graph-backend-installation.md).

While NornicDB is under evaluation, PCG keeps local content search isolated
from graph projection stalls. The local-authoritative ingester writes the
embedded-Postgres content index before attempting canonical graph writes, and
NornicDB canonical writes now run in bounded phase-group transactions instead
of one global grouped write. The timeout defaults to `15s` and can be tuned
for diagnostics with `PCG_CANONICAL_WRITE_TIMEOUT=2s`. The default
phase-group window is `500` statements and can be tuned with
`PCG_NORNICDB_PHASE_GROUP_STATEMENTS=<positive integer>` during repo-scale
dogfood runs. Neo4j production writes keep the grouped canonical path and are
not affected by this local-authoritative guardrail.

The current local-authoritative canonical entity path uses the narrowest shape
that the active backend has proven correct. Backends with correct node-only
batched `MERGE` support can separate entity node upserts from
`phase=entity_containment`. The pinned NornicDB release still uses a
file-scoped combined entity write: each statement matches the `File` anchor
with `$file_path`, unwinds entity rows for that file, upserts nodes, and
attaches `CONTAINS` in the same statement. A patched NornicDB binary that
supports row-safe `SET += row.props` in the generalized `UNWIND/MERGE` hot
path can opt into `PCG_NORNICDB_BATCHED_ENTITY_CONTAINMENT=true`, which batches
entity rows across files with `MERGE (n {uid: row.entity_id}) ... MATCH
(f {path: row.file_path}) ... MERGE (f)-[:CONTAINS]->(n)`. Do not enable that
switch with the current pinned binary. The `nornicdb entity label summary` log
includes `phase` so operators can tell which entity-write lane is active and
where repo-scale time is going.

NornicDB exposes explicit Bolt transaction hooks, but PCG does not enable
grouped canonical writes for normal laptop runs until the PCG Neo4j-driver
conformance matrix proves rollback, timeout, and no-partial-write behavior on
the PCG canonical workload. For adapter conformance only, set:

```bash
PCG_NORNICDB_CANONICAL_GROUPED_WRITES=true
```

That switch exposes the same grouped-write surface used by Neo4j while still
bounding the call with `PCG_CANONICAL_WRITE_TIMEOUT`. Leave it unset for
day-to-day `local_authoritative` coding. If you must use it for manual
conformance, use a disposable `PCG_HOME` / workspace data root.

The current safety probe is deliberately conservative:

```bash
PCG_NORNICDB_BINARY=/tmp/nornicdb-headless \
  go test ./cmd/pcg -run TestNornicDBGroupedWriteSafetyProbe -count=1 -v
```

The 2026-04-23 run against the rebuilt linuxdynasty-fork headless binary
`/tmp/nornicdb-headless-pcg-rollback` (`v1.0.42-hotfix`) proved that grouped
writes can commit a PCG repository/file/function shape, grouped rollback,
clean explicit rollback, and failed-statement explicit rollback all report
marker count `0` on the Neo4j-driver path, and the timeout probe leaves no
partial write. The stricter rollback promotion gate is:

```bash
PCG_NORNICDB_BINARY=/tmp/nornicdb-headless-pcg-rollback \
PCG_NORNICDB_REQUIRE_GROUPED_ROLLBACK=true \
  go test ./cmd/pcg -run TestNornicDBGroupedWriteRollbackConformance -count=1 -v
```

Do not promote NornicDB grouped canonical writes for normal laptop runs until
the fixed NornicDB binary is release-backed and broader adapter conformance
passes. Neo4j production grouped writes are unaffected.

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
Use `pcg graph logs [--workspace-root <path>]` to print that file without
manually deriving the workspace ID.

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

1. `pcg graph status` — did PCG discover the expected NornicDB binary from
   `PCG_NORNICDB_BINARY`, `${PCG_HOME}/bin/nornicdb-headless`, or `PATH`?
   If discovery reports not installed, verify the candidate binary prints a
   `NornicDB ...` version string or install it with
   `pcg install nornicdb --from <source>`.
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

### Content search works but graph-backed answers are degraded

This is expected during NornicDB evaluation if a canonical graph write times
out. MCP/CLI code-search tools that can answer from the content index should
still return results with a truth envelope such as
`basis=content_index` and `profile=local_authoritative`. Graph-backed
capabilities remain degraded until the graph projection succeeds or the
workspace is re-indexed after the backend issue is fixed.

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

## Schema dialect routing

`PCG_GRAPH_BACKEND` also controls graph schema bootstrap. PCG does not fork
the reducer, query handlers, or MCP tools per backend; it routes only the DDL
surface through a backend schema dialect:

- `neo4j` receives the shared production schema unchanged.
- `nornicdb` receives the NornicDB-compatible schema rendering. Current
  NornicDB rejects PCG's composite `IS UNIQUE` constraints, and PCG does not
  translate those constraints to `IS NODE KEY` because node keys require every
  participating property while some semantic labels are intentionally sparse.
  The NornicDB dialect therefore skips unsupported composite uniqueness DDL and
  relies on the separate `uid` uniqueness constraints for canonical merge
  identity.
- NornicDB intentionally skips Neo4j's multi-label
  `CREATE FULLTEXT INDEX` fallback because NornicDB only verified the
  procedure-based multi-label fulltext path.

The opt-in verification gate is:

```bash
PCG_NORNICDB_BINARY=/absolute/path/to/nornicdb-headless \
  go test ./cmd/pcg -run TestNornicDBSchemaAdapterVerification -count=1 -v
```

That test executes the rendered NornicDB schema against a real sidecar. It is
not part of the default unit-test suite because it requires an installed graph
binary.

## Non-goals

- Running multiple graph backends simultaneously on one workspace. The
  workspace lock admits exactly one owner and exactly one graph backend
  at a time.
- Running the graph backend headless without a PCG owner. The sidecar is
  owned by the lightweight host, not by the user shell.
