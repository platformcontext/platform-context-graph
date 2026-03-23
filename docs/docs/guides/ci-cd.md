# CI/CD Integration

PCG can run in CI pipelines to catch dead code, excessive complexity, or other graph-detectable issues before merge.

## GitHub Actions Example

```yaml
name: Code Quality
on: [pull_request]
jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install PCG
        run: uv tool install platform-context-graph
      - name: Index
        run: pcg index .
      - name: Check complexity
        run: pcg analyze complexity --threshold 20 --fail-on-found
      - name: Check dead code
        run: pcg analyze dead-code --fail-on-found
```

### What the checks do

**Complexity check** — finds functions with cyclomatic complexity above the threshold. A threshold of 20 catches the worst offenders without being noisy on typical codebases. Output looks like:

```
Found 2 functions exceeding complexity threshold (20):
  src/tools/graph_builder.py:build_graph (complexity: 34)
  src/query/resolver.py:resolve_entity (complexity: 22)
```

**Dead code check** — finds functions that are defined but never called from any indexed code. Useful for catching abandoned code before it accumulates.

## Large-Scale Indexing

For repositories with 100,000+ lines of code:

1. **Use Neo4j** — FalkorDB Lite may run out of RAM on large graphs.
2. **Increase memory** — `NEO4J_dbms_memory_heap_max_size=4G`.
3. **Exclude test fixtures** — Add `tests/` to `.pcgignore` if test code inflates the graph without adding signal.

## See also

- [CLI Analysis Reference](../reference/cli-analysis.md)
- [Configuration](../reference/configuration.md)
- [.pcgignore](../reference/pcgignore.md)
