# Bundles

Indexing a large repository takes minutes. If you want to explore a well-known project — or share your indexed graph with a teammate — you should not have to wait for a full re-index. Bundles let you skip it.

A `.pcg` bundle is a portable file containing pre-indexed graph data and metadata. Export one from your machine, load one from the registry, or request one on demand — and the graph is ready to query immediately.

Bundles are also the explicit opt-in path for dependency internals. Normal repository indexing excludes vendored and dependency directories (`vendor/`, `node_modules/`) by default. If you want the internals of React or Flask in your graph, load a bundle instead of indexing `node_modules/`.

## Load a pre-indexed bundle

The PCG registry publishes weekly bundles for popular open source projects via GitHub releases (`bundles-*`).

```bash
# Search for what's available
pcg registry search react

# Download and load into your graph
pcg load react
```

The `load` command imports the bundle's graph data into your local database. Use `--clear` to replace existing data for that repo, or load additively by default.

## Export your own bundle

After indexing a repository locally, export it so others can skip the indexing step:

```bash
pcg bundle export my-project.pcg --repo /path/to/repo
```

Share the `.pcg` file directly, or upload it to a PCG server:

```bash
pcg bundle upload my-project.pcg --service-url http://localhost:8080
```

## Request an on-demand bundle

For projects not in the weekly pre-indexed set, request a build. This triggers a GitHub Actions workflow that indexes the repo and publishes the bundle to the `on-demand-bundles` release:

```bash
pcg registry request https://github.com/org/repo
```

Check back with `pcg registry search` once the workflow completes.

## Common flags

| Flag | Effect |
|------|--------|
| `--repo` | Scope export to a specific repository path |
| `--clear` | Replace existing graph data for the repo on load |
| `--no-stats` | Skip post-load statistics output |
| `--verbose` | Show detailed import progress |
| `--unique` | Deduplicate entities during import |

## When bundles help

- **Onboarding** — new engineers load pre-indexed bundles instead of waiting for a full index of every repo
- **Dependency internals** — get React, Django, or any library's call graph without indexing `node_modules/` in every app repo
- **Sharing snapshots** — distribute a graph state without asking everyone to index locally
- **CI caching** — export a bundle in CI and reuse it across pipeline stages

## Current limitations

Bundle workflows are CLI and HTTP today. MCP can load an existing bundle, but remote upload is a CLI + HTTP flow — there is no MCP tool for `bundle upload` yet.

## Next steps

- [CLI Reference](../reference/cli-reference.md) — full `pcg bundle` and `pcg registry` command docs
- [HTTP API](../reference/http-api.md) — programmatic bundle import endpoint
- [Quickstart](../getting-started/quickstart.md) — index your first repo from scratch
