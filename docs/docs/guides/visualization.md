# Visualizing the Graph

## Neo4j Browser (`pcg visualize`)

The `pcg visualize` command (alias `pcg v`) generates a URL that opens Neo4j Browser with a pre-filled Cypher query:

```bash
pcg visualize
```

This prints a URL like `http://localhost:7474/browser?cmd=edit&arg=MATCH...` that shows the immediate neighborhood of your indexed code.

Requires a running Neo4j instance (local or remote).

## Neo4j Bloom

If you use Neo4j Desktop, Bloom provides a richer exploration experience:

- Spatial zoom and pan across the graph
- Natural-language-style search (e.g., "Show me callers of X")
- Visual filtering by node type

Bloom is part of Neo4j Desktop and requires no additional PCG configuration.
