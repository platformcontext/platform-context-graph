# Start here

PCG has three common starting points.

If you want PCG on your laptop, start with [Run Locally](run-locally/index.md).
That page helps you choose between local binaries and Docker Compose.

If you want an assistant to query PCG, start with [Connect MCP](mcp/index.md).
You can use MCP against the local owner, the Compose service, or a deployed API.

If you are deploying PCG for a team, start with
[Deploy to Kubernetes](deploy/kubernetes/index.md). That path covers storage,
Helm, manifests, health checks, and production readiness.

## Which path should I pick?

| Goal | Start here |
| --- | --- |
| I want to develop PCG or run one workspace locally | [Local binaries](run-locally/local-binaries.md) |
| I want the full stack on my laptop | [Docker Compose](run-locally/docker-compose.md) |
| I want my assistant to use PCG | [Connect MCP](mcp/index.md) |
| I need to deploy PCG to Kubernetes | [Deploy to Kubernetes](deploy/kubernetes/index.md) |
| I already know PCG and need exact commands | [Reference](reference/cli-reference.md) |

## Storage at a glance

PCG officially supports NornicDB and Neo4j as graph backends. NornicDB is the
default. Postgres is the relational database for facts, queues, status, content,
and recovery data.
