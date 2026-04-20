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

## Next step

- If you want to start indexing locally, go to [Quickstart](quickstart.md).
- If you want to connect an AI client, go to [MCP Guide](../guides/mcp-guide.md).
- If you want to run PCG as a service, go to [Deployment Overview](../deployment/overview.md).
