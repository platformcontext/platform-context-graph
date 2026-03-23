# Content Package

Portable source retrieval and content-search helpers.

This package stores and retrieves source text independently from the graph database. Neo4j owns structure and relationships; this package owns source text and source search.

## What it does

- Stores indexed file and entity content in PostgreSQL during indexing
- Reads source from PostgreSQL for deployed API and MCP runtimes
- Falls back to the server workspace when PostgreSQL is absent or missing a row
- Exposes stable `repo_id + relative_path` and `entity_id` retrieval

## Example flow

1. Ingester indexes a repository and dual-writes file content to Postgres
2. API receives `get_file_content(repo_id, relative_path)`
3. Content service checks Postgres first, then workspace fallback
4. Response includes `source_backend` so the caller knows the source
