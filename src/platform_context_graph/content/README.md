# Content Package

Portable source retrieval and content-search helpers live here.

Responsibilities:
- store indexed file and entity content in PostgreSQL when configured
- read source directly from the server workspace when PostgreSQL is absent or missing a row
- expose stable `repo_id + relative_path` and `entity_id` retrieval helpers

This package is intentionally separate from the graph database code. Neo4j/Kuzu/Falkor own structure and relationships; the content package owns source text and source search.
