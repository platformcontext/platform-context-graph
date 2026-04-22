# Graph Backend Installation

PCG's `local_authoritative` profile and its Compose / production profiles
read the canonical graph through a **graph backend adapter**. The default
adapter today is Neo4j. PCG is also evaluating NornicDB as an alternative
backend. Adoption criteria live in
[ADR 2026-04-22 — NornicDB As Candidate Graph Backend](../adrs/2026-04-22-nornicdb-graph-backend-candidate.md).

This page documents how to install a graph backend locally so the PCG
lightweight host can run the `local_authoritative` profile without Docker
Compose.

## Backend selection

Set the graph backend explicitly via environment variable:

- `PCG_GRAPH_BACKEND=neo4j` — default, matches today's behavior
- `PCG_GRAPH_BACKEND=nornicdb` — opt in to the NornicDB adapter

Invalid values are rejected at startup. There is no silent default.

The backend axis is also surfaced optionally in responses as `truth.backend`
and in telemetry span / metric labels as `graph_backend`.

## Profile requirements

| Profile | Graph backend required |
| --- | --- |
| `local_lightweight` | None |
| `local_authoritative` | Yes, installed locally via the steps below |
| `local_full_stack` | Provided by Compose |
| `production` | Provided by Helm / Kubernetes |

## NornicDB install flow

PCG provides `pcg install nornicdb` to pin, download, and register a
NornicDB binary under `${PCG_HOME}/bin/` with a version pinned by the
installed PCG release.

```bash
pcg install nornicdb
```

The command performs, in order:

1. Reads the pinned NornicDB version from the PCG release manifest.
2. Chooses the correct artifact for the host OS / architecture.
3. Downloads the release tarball from the upstream release URL.
4. Verifies SHA-256 checksum against the manifest.
5. If the release manifest records a Sigstore / Cosign signature, verifies
   it. Unsigned artifacts refuse to install unless
   `--allow-unsigned` is passed explicitly.
6. Extracts to `${PCG_HOME}/bin/nornicdb`.
7. Writes `${PCG_HOME}/graph-backends/nornicdb/manifest.json` recording the
   installed version, checksum, signature status, and install timestamp.

### Upgrade

```bash
pcg install nornicdb --version <semver>
```

Replaces the installed binary with the requested version. The previous
binary is retained at `${PCG_HOME}/bin/nornicdb.previous` for rollback.

### Rollback

```bash
pcg install nornicdb --rollback
```

Restores the `.previous` binary if present.

### Offline install

```bash
pcg install nornicdb --from <path-to-tarball>
```

Skips the download step. Still verifies checksum against the tarball and,
if present, the accompanying signature file.

### Uninstall

```bash
pcg install nornicdb --uninstall
```

Removes the binary, the graph backend manifest entry, and (with
`--purge-data`) the per-workspace `graph/nornicdb/` data directories under
all local workspaces.

## Supply chain

The PCG release manifest is the source of truth for:

- pinned graph-backend version per PCG release
- artifact SHA-256 checksum
- signing policy (`required`, `preferred`, `disabled`)
- upstream release URL template

Operators who want a stricter policy can override via:

- `PCG_GRAPH_BACKEND_ARTIFACT_URL` — custom mirror
- `PCG_GRAPH_BACKEND_ALLOWED_VERSIONS` — allowlisted semver ranges

## Verification

After install, verify with:

```bash
pcg doctor
pcg graph status
```

Both should report the graph backend as present, the binary path, and the
installed version.

## Non-goals

- Installing Neo4j. Neo4j remains an operator responsibility in Compose and
  Kubernetes.
- Running the graph backend as a system service. The sidecar is a
  user-level process tied to the PCG lightweight host lifecycle.
- Bundling the graph backend into the `pcg` binary. See the rejection in
  [ADR 2026-04-20](../adrs/2026-04-20-embedded-local-backends-desktop-mode.md)
  and the sidecar exception in
  [ADR 2026-04-22](../adrs/2026-04-22-nornicdb-graph-backend-candidate.md).
