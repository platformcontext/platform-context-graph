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
   `pcg install nornicdb --from <source>`
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

## Managed install

Today there are two truthful install paths:

- bare `pcg install nornicdb` for host platforms that PCG's embedded release
  manifest knows how to resolve
- explicit `--from` install for everything else

The current pinned bare install is intentionally narrow: it resolves only
real published assets. As of 2026-04-23 that means upstream
`orneryd/NornicDB` macOS arm64 `lite.pkg` for `dev` builds of PCG. The
linuxdynasty fork still does not publish native release assets, so grouped
write conformance remains a manual `--from` path.

Explicit `--from` installs can consume any of these artefacts:

- a local NornicDB binary
- a local `.tar`, `.tar.gz`, or `.tgz` archive containing `nornicdb-headless`
  or `nornicdb`
- a local `.pkg` containing `/usr/local/bin/nornicdb` or `nornicdb-headless`
- an `http://`, `https://`, or `file://` URL to one of those artefacts

```bash
# Bare pinned install when the host platform is covered by the embedded
# release manifest.
pcg install nornicdb

pcg install nornicdb --from /absolute/path/to/nornicdb-headless

# Local release archive.
pcg install nornicdb \
  --from /absolute/path/to/nornicdb-headless-darwin-arm64.tar.gz \
  --sha256 <expected-archive-sha256>

# Local or remote macOS package.
pcg install nornicdb \
  --from /absolute/path/to/NornicDB-1.0.42-hotfix-arm64-lite.pkg \
  --sha256 <expected-package-sha256>

# Remote release artefact URL.
pcg install nornicdb \
  --from https://example.com/releases/nornicdb-headless-darwin-arm64.tar.gz \
  --sha256 <expected-archive-sha256>

# Replace an existing managed binary.
pcg install nornicdb --from /absolute/path/to/nornicdb-headless --force
```

The command performs, in order:

1. If `--from` is omitted, resolves the host OS / architecture against the
   embedded pinned release manifest and chooses the recorded URL + SHA-256.
2. Resolves `--from` to a local path or downloads the remote artefact to a
   temporary file.
3. If the source is a tar archive, extracts the first usable
   `nornicdb-headless` entry, or falls back to `nornicdb` when the archive
   only contains the full binary.
4. If the source is a macOS `.pkg`, expands the package and extracts the
   packaged `usr/local/bin/nornicdb` payload without installing the package
   system-wide.
5. Verifies the resulting binary by running `<binary> version` and requiring a
   `NornicDB ...` version string.
6. Computes the source artefact SHA-256 checksum and compares it with
   `--sha256` when provided.
7. Copies the verified binary to `${PCG_HOME}/bin/nornicdb-headless` with
   executable permissions.
8. Writes
   `${PCG_HOME}/graph-backends/nornicdb/manifest.json` with backend,
   version, installed-binary checksum, source checksum, source kind, source
   locator, install mode, and install timestamp.

After installation, `pcg graph status` should report `graph_installed: true`
and the managed binary path.

When the pinned manifest does not cover the current host platform, bare install
fails loudly with a structured error and the laptop flow is still either:

- build `bin/nornicdb-headless` locally and install from that path, or
- point `--from` at a manually produced archive / hosted artefact URL

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

## Current pinned bare install flow

The no-argument installer now reads an embedded release manifest keyed by the
installed PCG version and host OS / architecture, then downloads and installs
that pinned artefact under `${PCG_HOME}/bin/`.

```bash
pcg install nornicdb
```

Current caveats:

- the manifest is embedded in PCG, not yet fetched remotely
- only platforms with real pinned assets are supported
- signature verification is not implemented yet
- the current `dev` manifest entry targets upstream `orneryd/NornicDB`
  `v1.0.42-hotfix` macOS arm64 `lite.pkg`
- the fork-backed fixed grouped-write binary is still a manual `--from`
  install until native fork releases exist or the fix lands upstream

## Planned manifest hardening

Still planned:

- remote or release-synchronized manifest updates
- Sigstore / Cosign signature verification
- explicit unsigned-artifact policy
- broader Linux / macOS amd64 coverage once those assets are genuinely
  published

### Upgrade

```bash
pcg graph upgrade --from /absolute/path/to/nornicdb-headless
```

Replaces the installed binary from a verified local executable after the
workspace graph has been stopped. Release-backed semver upgrades remain future
work.

### Rollback

```bash
pcg install nornicdb --rollback
```

Restores the `.previous` binary if present.

### Offline archive or package install

```bash
pcg install nornicdb --from <path-to-tarball-or-pkg>
```

This is now supported for tar archives and macOS packages, but signature verification for offline
artefacts remains future work.

### Uninstall

```bash
pcg install nornicdb --uninstall
```

Removes the binary, the graph backend manifest entry, and (with
`--purge-data`) the per-workspace `graph/nornicdb/` data directories under
all local workspaces.

## Supply chain

The embedded PCG release manifest is the source of truth for:

- pinned graph-backend version per PCG release
- artifact SHA-256 checksum
- upstream release URL

Still planned before promotion:

- signing policy (`required`, `preferred`, `disabled`)
- Sigstore / Cosign verification metadata
- externalized manifest publication / refresh strategy

The stricter operator override layer is not wired yet.

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
