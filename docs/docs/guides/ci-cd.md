# CI/CD Integration

Catch dead code before it reaches main. PCG can run in CI pipelines to flag
graph-detectable issues at pull request time without requiring manual review
for the mechanical checks.

## GitHub Actions example

```yaml
name: Code Quality
on: [pull_request]
jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version-file: go/go.mod
      - name: Build PCG
        run: |
          cd go
          go build -o ../pcg ./cmd/pcg
      - name: Index the repo
        run: ./pcg index .
      - name: Check dead code
        run: ./pcg analyze dead-code --repo-id repository:r_ab12cd34 --exclude @app.route --fail-on-found
```

### What each step does

**Index the repo** — `pcg index .` parses source code, builds the call graph, and stores it locally. For a typical service repo this takes 10-30 seconds.

**Check dead code** — `pcg analyze dead-code --repo-id repository:r_ab12cd34 --exclude @app.route --fail-on-found` finds entities that have no incoming `CALLS`, `IMPORTS`, or `REFERENCES` edges after decorator exclusions are applied. The command exits non-zero when candidates remain, failing the PR check.

Threshold-based complexity gating is available through the Go CLI today via
`pcg analyze complexity`. If you want CI to enforce a threshold, treat that as
an optional policy layer on top of the shipped command rather than a missing
runtime-parity feature.

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
4. **Reuse stable artifacts** — cache the built PCG binary and any database or bundle artifacts your pipeline already produces, instead of rebuilding them in every stage

## See also

- [CLI Analysis Reference](../reference/cli-analysis.md) — all `pcg analyze` subcommands
- [Configuration](../reference/configuration.md) — environment variables and settings
- [.pcgignore](../reference/pcgignore.md) — ignore file syntax
- [Bundles](bundles.md) — import and search prebuilt graph bundles
