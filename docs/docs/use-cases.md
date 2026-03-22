# Use Cases

PlatformContextGraph is useful both when you only care about code relationships and when you need end-to-end code-to-cloud context.

## Code-only workflows

- **Find callers and callees.** Ask what calls a function or what a function depends on before changing it.
- **Refactor safely.** Use graph-backed impact analysis instead of guessing from grep output.
- **Find dead or complex code.** Use the CLI, MCP, or HTTP API to target code health issues quickly.
- **Onboard faster.** Give AI or new contributors a map of the codebase instead of starting from zero.

## Code-to-cloud workflows

- **Trace a workload to infrastructure.** Start from a service or workload and follow images, Kubernetes resources, and cloud resources.
- **Trace a resource back to code.** Start from a database, queue, image, or Terraform resource and walk back to repositories and workloads.
- **Understand shared infrastructure.** See which workloads consume a shared cluster, queue, or other foundation resource.
- **Compare environments.** Find what differs between stage and prod for the same logical workload.

## AI-assisted engineering workflows

- **Development:** give the assistant real graph context while adding new functionality.
- **Debugging:** let the assistant reason about callers, deployment shape, and shared dependencies.
- **Troubleshooting:** connect runtime resources and IaC back to code.
- **Re-architecture:** understand what has to move together before changing service boundaries.

## Why this is better than point tools

Traditional tools answer one slice of the problem:

- grep answers text search
- linters answer style or static checks
- cloud consoles answer only runtime state
- IaC repos answer only declared intent

PCG connects those slices into one queryable model so engineers and AI agents can make better decisions with less context switching.
