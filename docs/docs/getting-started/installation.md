# Installation

Install PCG in the way that matches how you plan to use it.

## Option 1: Build from source

Clone the repository and build the Go binaries:

```bash
cd go && go build -o bin/ ./cmd/pcg
export PATH="$PWD/bin:$PATH"
pcg --help
```

## Option 2: Docker

Run the full platform stack with Docker Compose:

```bash
docker compose up --build
```

This builds a single Go-only image and starts all platform services (API,
ingester, reducer, bootstrap-index) along with Neo4j, Postgres, OTEL
collector, and Jaeger.

## Database setup

For the deployable-service and Kubernetes path, use **Neo4j**.

For local experiments, you can still use the lightweight local backend where supported, but the public deployment contract assumes external Neo4j.

If you want a local Neo4j helper:

```bash
pcg neo4j setup
```

See [Neo4j Setup](../guides/neo4j-setup.md) for the wizard behavior and current expectations.

## Verify the install

Run:

```bash
pcg doctor
```

You should be able to see the CLI and database checks complete successfully before moving on.

## Local-authoritative graph sidecar

If you want laptop-native authoritative graph queries without Docker Compose,
install a NornicDB artefact for the `local_authoritative` profile:

```bash
# Pinned bare install when your host platform is covered by PCG's embedded
# release manifest.
pcg install nornicdb

# Local binary build.
pcg install nornicdb --from /absolute/path/to/nornicdb-headless

# Local or remote release archive.
pcg install nornicdb --from /absolute/path/to/nornicdb-headless-darwin-arm64.tar.gz
pcg install nornicdb --from https://example.com/releases/nornicdb-headless-darwin-arm64.tar.gz --sha256 <expected-sha256>

# macOS package artefact.
pcg install nornicdb --from /absolute/path/to/NornicDB-1.0.42-hotfix-arm64-lite.pkg --sha256 <expected-sha256>
```

The laptop default is still the headless artefact. Bare
`pcg install nornicdb` now pins the rollback-fixed linuxdynasty fork headless
release when your host is covered by the embedded manifest. Bare
`pcg install nornicdb --full` only works when that manifest publishes a
matching fixed full binary for your host; until then, use `--from` for the
larger full binary. If the current host is not covered, the bare install
commands fail loudly and you should use `--from`.

## Next step

- If you want to start indexing locally, go to [Quickstart](quickstart.md).
- If you want to connect an AI client, go to [MCP Guide](../guides/mcp-guide.md).
- If you want to run PCG as a service, go to [Deployment Overview](../deployment/overview.md).
