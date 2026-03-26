# Why PCG

## The Problem

When you refactor a service, your AI assistant sees the code in front of it. It does not see the Terraform module that provisions the database, the ArgoCD application that deploys the workload, the Kubernetes manifest that configures replicas and secrets, or the three other services whose queue consumers break if you change the API contract.

That context exists. It is spread across your repositories, Helm charts, Terraform state, ArgoCD apps, cloud consoles, and the heads of your senior engineers. But nothing connects it into a single queryable model — so engineers stitch it together by hand, every time, or skip the investigation and discover the blast radius in production.

Code search tools index code. IaC tools manage infrastructure. Service catalogs track ownership. None of them answer the question that actually matters during feature work, refactors, and incidents: **what connects to what, and what breaks if I change it?**

## What PCG Does

PlatformContextGraph builds a graph that connects source code, infrastructure definitions, and running workloads across your entire platform.

It indexes:

- **Source code** — functions, classes, imports, call graphs across 30+ languages (tree-sitter)
- **Infrastructure-as-code** — Terraform/HCL, Kubernetes manifests, Helm charts, Kustomize overlays, CloudFormation
- **Deployment topology** — ArgoCD Applications and ApplicationSets, Crossplane XRDs and Claims
- **Cross-repo relationships** — module sources, image references, repo URLs, shared resources

The result is a graph you can query from the CLI, through MCP in your AI assistant, or via HTTP API. Same capabilities, same query model, three interfaces.

## What Makes PCG Different

Unlike code-only search tools, PCG treats infrastructure as a first-class citizen. Unlike service catalogs, it is built from your actual code and IaC — not manually maintained metadata. Unlike grepping across repos, it understands relationships: what deploys what, what provisions what, what consumes what, and what breaks when something changes.

Key capabilities no other open source tool combines:

- **`find_blast_radius`** — transitive dependency analysis across repos and infrastructure boundaries
- **`trace_deployment_chain`** — follow a service from ArgoCD through K8s resources to the repos and code that define them
- **`trace_resource_to_code`** — trace a cloud resource back to the Terraform module and repository that owns it
- **`compare_environments`** — diff the dependency surface of a workload between prod and staging
- **`find_change_surface`** — see what is impacted before you merge
- **`explain_dependency_path`** — understand why two entities are connected, with evidence for each hop

## Who It's For

### Backend engineers

Before modifying a service, you need to understand callers, dependencies, workloads, downstream consumers, and likely blast radius. PCG answers these questions from the graph instead of requiring manual investigation across repos and IaC.

### Platform / DevOps / SRE

Platform teams are constantly asked how workloads connect to infrastructure, what is shared, and what differs between environments. PCG gives you — and the AI assistants your developers use — a real answer instead of tribal knowledge.

### New engineers

Onboarding into a complex system usually means interrupting senior engineers for context about deployment topology, shared infrastructure, and cross-service dependencies. PCG lets new team members query that context directly and get grounded answers from AI assistants on day one.

## Why MCP Matters

MCP is how most engineers will experience PCG.

Without MCP, you have a useful graph with a CLI and API. With MCP, that graph becomes available inside the AI workflow where engineers are already asking questions — Claude, Cursor, VS Code, or any MCP-compatible tool.

The difference: your AI assistant stops guessing from a single file and starts querying the actual dependency graph. It can answer "what breaks if I change this?" with evidence from the graph, not hallucinated assumptions from a partial code snapshot.

Questions that work today:

- "Who calls this function across all indexed repos?"
- "What workload uses this queue in prod?"
- "Trace this RDS instance back to the Terraform module and the repos that reference it."
- "What changes if I modify this service?"
- "Compare stage and prod for this workload — what resources differ?"
- "Explain how this repo connects to the shared infrastructure platform."

## A Real Workflow

**Scenario:** You need to refactor the payment service's API contract.

1. **Scope the change** — `find_blast_radius payment-service` shows 4 downstream repos, 2 shared Terraform modules, and a Crossplane claim.
2. **Understand the deployment** — `trace_deployment_chain payment-service` shows the ArgoCD app, K8s Deployment, and backing resources.
3. **Check environment differences** — `compare_environments payment-service prod staging` reveals a config divergence in the SQS queue policy.
4. **Trace a shared resource** — `trace_resource_to_code payment-db` shows the RDS module in `terraform-modules/rds` is also used by `billing-service` and `analytics-pipeline`.
5. **Ship with confidence** — you know the blast radius before you open the PR, not after the page.

## Open Source

PCG is MIT licensed, self-hosted, and does not phone home. The graph runs on Neo4j (production), FalkorDB, or KuzuDB (local). Language parsers are spec-driven — add a new language by writing a YAML spec and tree-sitter queries.

Contributions welcome: new language parsers, IaC formats, query capabilities, and deployment patterns.

## Start Here

- [Quickstart](getting-started/quickstart.md) — index a repo and run your first query
- [MCP Guide](guides/mcp-guide.md) — connect PCG to your AI assistant
- [HTTP API](reference/http-api.md) — automation and service-to-service access
- [Use Cases](use-cases.md) — detailed workflow examples
- [Architecture](architecture.md) — how PCG works under the hood
