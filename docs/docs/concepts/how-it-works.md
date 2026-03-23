# How It Works

Understanding the pipeline helps you ask better questions and interpret the answers correctly.

## 1. Discovery

PCG discovers files and assets from repositories and mono-folders while pruning ignored and hidden cache trees such as `.git`, `.terraform`, and `.terragrunt-cache`.

## 2. Parsing

PCG parses:

- source code
- repository metadata
- infrastructure definitions
- deployment artifacts such as Helm, Kubernetes, and Argo CD manifests

## 3. Graph construction

The parser output becomes graph nodes and edges. Some are direct facts, and some are higher-confidence inferences built from multiple signals.

- **Direct facts:** files, functions, classes, imports, manifests, Terraform resources
- **Inferred relationships:** workload-to-resource usage, service aliases, deployment chains, shared infra consumption

## 4. Storage

The graph is written to the backing database and becomes queryable through CLI, MCP, and HTTP.

## 5. Querying

Queries resolve from user-friendly input into canonical entities such as repositories, workloads, workload instances, or cloud resources.

A Cypher query like `MATCH (caller)-[:CALLS]->(callee {name: 'process_payment'}) RETURN caller` is one kind of question. PCG also answers:

- which workloads use a shared database
- which Terraform module provisions a resource
- what differs between environments
- what code is affected by a resource or workload change
