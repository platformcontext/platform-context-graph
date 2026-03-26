# CI/CD Integration

Catch complexity spikes and dead code before they reach main. PCG runs in CI pipelines to flag graph-detectable issues at pull request time — no manual review needed for the mechanical checks.

## GitHub Actions example

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
      - name: Index the repo
        run: pcg index .
      - name: Check complexity
        run: pcg analyze complexity --threshold 20 --fail-on-found
      - name: Check dead code
        run: pcg analyze dead-code --fail-on-found
```

### What each step does

**Index the repo** — `pcg index .` parses source code, builds the call graph, and stores it locally. For a typical service repo this takes 10-30 seconds.

**Check complexity** — `pcg analyze complexity --threshold 20 --fail-on-found` finds functions with cyclomatic complexity above 20. This catches the worst offenders without being noisy on typical codebases. Output:

```
Found 2 functions exceeding complexity threshold (20):
  src/tools/graph_builder.py:build_graph (complexity: 34)
  src/query/resolver.py:resolve_entity (complexity: 22)
```

**Check dead code** — `pcg analyze dead-code --fail-on-found` finds functions that are defined but never called from any indexed code. Catches abandoned code before it accumulates.

Both checks exit non-zero when issues are found, failing the PR check.

## Excluding paths with .pcgignore

Some directories inflate the graph without adding signal. Create a `.pcgignore` file at your repo root:

```
tests/fixtures/
docs/
scripts/
*.generated.py
```

Syntax follows `.gitignore` patterns. See the [.pcgignore reference](../reference/pcgignore.md) for details.

## Large-scale indexing

For repositories with 100,000+ lines of code:

1. **Use Neo4j** — FalkorDB Lite may run out of RAM on large graphs
2. **Increase memory** — `NEO4J_dbms_memory_heap_max_size=4G`
3. **Exclude test fixtures** — add `tests/` to `.pcgignore` if test code inflates the graph without adding signal
4. **Cache the index** — export a bundle in CI and reuse it across pipeline stages (see [Bundles](bundles.md))

## See also

- [CLI Analysis Reference](../reference/cli-analysis.md) — all `pcg analyze` subcommands
- [Configuration](../reference/configuration.md) — environment variables and settings
- [.pcgignore](../reference/pcgignore.md) — ignore file syntax
- [Bundles](bundles.md) — cache and share indexed graphs
