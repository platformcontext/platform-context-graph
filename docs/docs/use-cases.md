# Use Cases

PlatformContextGraph works for code-only questions and for end-to-end code-to-cloud tracing.

## Code-only workflows

- **Find callers and callees.** See what calls a function or what a function depends on before changing it.
- **Refactor safely.** Use graph-backed impact analysis instead of guessing from grep output.
- **Find dead or complex code.** Target code health issues through the CLI, MCP, or HTTP API.
- **Onboard faster.** Give AI assistants or new contributors a map of the codebase instead of starting from zero.

## Code-to-cloud workflows

- **Trace a workload to infrastructure.** Start from a service or workload and follow images, Kubernetes resources, and cloud resources.
- **Trace a resource back to code.** Start from a database, queue, image, or Terraform resource and walk back to repositories and workloads.
- **Understand shared infrastructure.** See which workloads consume a shared cluster, queue, or foundation resource.
- **Compare environments.** Find what differs between stage and prod for the same logical workload.

## AI-assisted engineering

- **Development:** Give the assistant real graph context while building features.
- **Debugging:** Let the assistant reason about callers, deployment shape, and shared dependencies.
- **Troubleshooting:** Connect runtime resources and IaC back to code.
- **Re-architecture:** Understand what has to move together before changing service boundaries.

## Why this beats point tools

Traditional tools answer one slice:

- grep answers text search
- Linters answer style or static checks
- Cloud consoles answer runtime state
- IaC repos answer declared intent

PCG connects those slices into one queryable model so engineers and AI agents can make better decisions with less context switching.
