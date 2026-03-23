# Query Package

Read-side graph queries and context assembly. This package answers questions without mutating graph state.

## What each submodule answers

| Submodule | Example questions |
| :--- | :--- |
| `code.py` | "Who calls `process_payment`?" / "Find dead code" |
| `compare.py` | "What differs between stage and prod?" |
| `entity_resolution.py` | "Resolve 'payments prod rds' to a canonical entity" |
| `infra.py` | "Find all Terraform resources in the payments repo" |
| `context/` | "Give me full context for the payments-api workload" |
| `impact/` | "What's the blast radius if I change this module?" |
| `repositories/` | "List indexed repos" / "Show stats for this repo" |
| `content.py` | "Show me the source for this file" / "Search for this string" |
