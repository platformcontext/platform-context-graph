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

## Current local-authoritative requirement

Today, `local_authoritative` requires a verified NornicDB binary. PCG
defaults to the laptop-friendly headless artifact and discovers binaries in
this order:

1. `PCG_NORNICDB_BINARY`
2. `${PCG_HOME}/bin/nornicdb-headless` installed by
   `pcg install nornicdb --from <path>`
3. `nornicdb-headless` on `PATH`
4. `nornicdb` on `PATH`

The environment variable stays first so advanced users can temporarily test a
different binary without mutating the managed install.

The full `nornicdb` binary is supported when users opt in with
`PCG_NORNICDB_BINARY` or place it on `PATH`, but it is not the local-laptop
default because it can carry UI / local-LLM payloads and is materially
larger. PCG still starts the process with `nornicdb serve --headless` and
`NORNICDB_HEADLESS=true`; those runtime flags disable UI endpoints but do
not make the full binary smaller. Hosted evaluation and future production
packaging may use the full deployment artifact when that profile is
promoted.

PCG verifies candidate binaries by running `<binary> version` and requiring a
`NornicDB ...` version string. A random admin password is generated once per
workspace graph data root and stored in
`graph/nornicdb/pcg-credentials.json` with `0600` permissions. The live owner
copies it to `owner.json` so attach processes can connect without a hardcoded
shared secret.

## Managed local-file install

The current installer slice is intentionally local-file only. It does not
download from the internet or make supply-chain claims before the release
manifest and signature policy are real.

```bash
pcg install nornicdb --from /absolute/path/to/nornicdb-headless

# Optional checksum guard for copied artifacts.
pcg install nornicdb \
  --from /absolute/path/to/nornicdb-headless \
  --sha256 <expected-sha256>

# Replace an existing managed binary.
pcg install nornicdb --from /absolute/path/to/nornicdb-headless --force
```

The command performs, in order:

1. Verifies the source path is an executable NornicDB binary by running
   `<binary> version` and requiring a `NornicDB ...` version string.
2. Computes the source SHA-256 checksum and compares it with `--sha256` when
   provided.
3. Copies the source binary to `${PCG_HOME}/bin/nornicdb-headless` with
   executable permissions.
4. Writes
   `${PCG_HOME}/graph-backends/nornicdb/manifest.json` with backend,
   version, checksum, source path, install mode, and install timestamp.

After installation, `pcg graph status` should report `graph_installed: true`
and the managed binary path.

## Manual source build options

A developer can build or provide the binary in one of these ways before
calling `pcg install nornicdb --from ...`:

```bash
# Preferred laptop path from a NornicDB checkout when plugin prerequisites
# are installed.
make build-headless
pcg install nornicdb --from /absolute/path/to/NornicDB/bin/nornicdb-headless

# Reliable local fallback when optional local-LLM/plugin prerequisites are
# absent on the laptop.
go build -tags 'noui nolocalllm' -o /tmp/nornicdb-headless ./cmd/nornicdb
pcg install nornicdb --from /tmp/nornicdb-headless

# Explicit opt-in to the larger full binary.
PCG_NORNICDB_BINARY=/absolute/path/to/nornicdb pcg graph status

# Runtime-only headless mode for a full binary. This disables UI endpoints
# but does not reduce binary size.
NORNICDB_HEADLESS=true nornicdb serve
nornicdb serve --headless
```

Container builds are useful for hosted or Compose-style experiments, but the
current laptop sidecar launches a local binary:

```bash
docker build --build-arg HEADLESS=true -f docker/Dockerfile.arm64-metal .
```

## Planned release-backed install flow

PCG is still planning a release-backed installer mode that pins, downloads,
and registers the headless NornicDB laptop artifact under `${PCG_HOME}/bin/`
with a version pinned by the installed PCG release.

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
6. Extracts to `${PCG_HOME}/bin/nornicdb-headless`.
7. Writes `${PCG_HOME}/graph-backends/nornicdb/manifest.json` recording the
   installed version, checksum, signature status, and install timestamp.

### Upgrade

```bash
pcg install nornicdb --version <semver>
```

Replaces the installed binary with the requested version. The previous
binary is retained at `${PCG_HOME}/bin/nornicdb-headless.previous` for
rollback.

### Rollback

```bash
pcg install nornicdb --rollback
```

Restores the `.previous` binary if present.

### Offline artifact install

```bash
pcg install nornicdb --from <path-to-tarball>
```

This future mode installs from a release tarball instead of a local executable
binary. It still verifies checksum against the tarball and, if present, the
accompanying signature file.

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

After managed install, verify with:

```bash
pcg graph status
```

When building directly from a local NornicDB checkout for laptop testing,
prefer the repository target when its optional plugin prerequisites are
available. If that target fails because local-LLM/plugin libraries are not
installed, use the direct no-UI/no-local-LLM fallback:

```bash
make build-headless
pcg install nornicdb --from /absolute/path/to/NornicDB/bin/nornicdb-headless
pcg graph status

go build -tags 'noui nolocalllm' -o /tmp/nornicdb-headless ./cmd/nornicdb
pcg install nornicdb --from /tmp/nornicdb-headless
pcg graph status
```

## Non-goals

- Installing Neo4j. Neo4j remains an operator responsibility in Compose and
  Kubernetes.
- Running the graph backend as a system service. The sidecar is a
  user-level process tied to the PCG lightweight host lifecycle.
- Bundling the graph backend into the `pcg` binary. See the rejection in
  [ADR 2026-04-20](../adrs/2026-04-20-embedded-local-backends-desktop-mode.md)
  and the sidecar exception in
  [ADR 2026-04-22](../adrs/2026-04-22-nornicdb-graph-backend-candidate.md).
