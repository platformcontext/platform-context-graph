# Use Cases

Every use case below is a question that takes minutes to answer manually — grepping across repos, reading Terraform state, checking ArgoCD, asking a senior engineer — and seconds with PCG.

## Before you merge

You are about to change a service's API contract. What breaks?

```bash
pcg analyze find-blast-radius payment-service
```

`find_blast_radius` walks transitive dependencies across repos and infrastructure boundaries: downstream services, shared Terraform modules, Crossplane claims, queue consumers. You see the full impact surface before you open the PR, not after the page.

To scope it to just the files and functions touched by a change:

```bash
pcg analyze find-change-surface --repo /path/to/repo --paths src/api/contracts.py
```

`find_change_surface` shows what depends on the specific code you modified — callers, importers, and infrastructure that references the changed module.

## During a production incident

A database is unhealthy. Which services use it, and how are they deployed?

`trace_resource_to_code` starts from a cloud resource and walks back through Terraform modules, repositories, and workloads:

```
→ trace_resource_to_code payment-db
  RDS instance: payment-db
  ← Terraform module: terraform-modules/rds (repo: infra-modules)
  ← Referenced by: payment-service/main.tf, billing-service/main.tf
  ← Workloads: payment-service (ArgoCD), billing-service (ArgoCD)
```

`trace_deployment_chain` goes the other direction — from a service name through ArgoCD, K8s resources, images, and backing infrastructure.

For MCP and API callers, start with the top-level `story` field from `trace_deployment_chain` or `get_repo_summary`, then drill into `deployment_overview` and the detailed fields if you need the exact evidence rows.

That applies to controller-driven automation estates too. If a platform uses Jenkins plus Ansible, start with `story`, then inspect `deployment_overview`, `delivery_paths`, and `controller_driven_paths` before dropping to raw workflow, playbook, or inventory evidence.

## Onboarding a new engineer

Day one. A new engineer needs to understand how the payment service fits into the platform.

`get_service_context` returns a structured overview: what the service depends on, what depends on it, how it is deployed, and what infrastructure it consumes. `get_repo_context` does the same scoped to a single repository.

To understand a specific connection:

```
→ explain_dependency_path payment-service shared-rds-cluster
  payment-service → main.tf (module "db") → terraform-modules/rds → shared-rds-cluster
  Evidence: module source URL match + resource name correlation
```

`explain_dependency_path` shows why two entities are connected, with evidence for each hop. No tribal knowledge required.

## Comparing environments

Staging is broken but prod works. What is different?

```
→ compare_environments payment-service prod staging
  Resources only in prod:
    - sqs-queue: payment-dlq (dead letter queue)
  Config differences:
    - replicas: 3 (prod) vs 1 (staging)
    - env.DATABASE_URL: prod-rds vs staging-rds
```

`compare_environments` diffs the dependency surface of a workload between two environments — resources, config, and infrastructure references.

## AI-assisted workflows

All of these tools are available through MCP. Your AI assistant can call them directly instead of guessing from a single file:

- "What breaks if I change this?" → `find_blast_radius`
- "How is this service deployed?" → `trace_deployment_chain`
- "What provisions this database?" → `trace_resource_to_code`
- "Explain how these two things connect" → `explain_dependency_path`
- "What differs between prod and staging?" → `compare_environments`

See the [MCP Guide](guides/mcp-guide.md) for setup.

## Next steps

- [Why PCG](why-pcg.md) — the problem this solves and how PCG is different
- [Quickstart](getting-started/quickstart.md) — index a repo and run your first query
- [MCP Cookbook](reference/mcp-cookbook.md) — detailed MCP query examples
