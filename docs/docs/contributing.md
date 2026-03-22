# Contributing to PlatformContextGraph

PlatformContextGraph is now a code-to-cloud context graph with three first-class surfaces:

- CLI
- MCP
- OpenAPI-backed HTTP API

Contributions should preserve that shared model instead of adding one-off behavior to only one surface.

## Contributor Rules

- Keep pull requests focused on one problem.
- Update or add tests whenever behavior changes.
- Keep handwritten Python modules under `src/` at 500 lines or fewer.
- Add Google-style docstrings to handwritten Python modules, classes, methods, and functions under `src/`.
- Use lower-case snake_case names for new Python files.
- Keep package boundaries readable. If you add a meaningful new package directory, add a short `README.md` for contributor orientation.

## Source Layout

The Python package is organized by responsibility under `src/platform_context_graph/`.

- `api/`: FastAPI application and routers
- `cli/`: Typer entrypoints, command registration, setup flows, and visualization helpers
- `core/`: database and runtime plumbing
- `domain/`: shared entity and response models
- `observability/`: OTEL bootstrap, runtime state, and metrics helpers
- `query/`: shared read/query layer for CLI, MCP, and HTTP
- `runtime/`: repo sync and indexing runtime orchestration
- `tools/`: parsers, graph builder, and analysis helpers

See [Source Layout](reference/source-layout.md) for a more detailed package map.

## Development Setup

1. Fork the repository.
2. Install the development environment:

```bash
uv sync
```

3. Create a feature branch.

```bash
git checkout -b codex/my-change
```

## Required Local Checks

Run these before opening a pull request:

```bash
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
uv run black --check src tests
./tests/run_tests.sh fast
```

If you change docs or public contracts, also run:

```bash
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

## Indexing And Runtime Notes

- Local indexing is CLI-driven, for example `pcg index .`.
- Kubernetes indexing is deployment-managed through the Helm runtime:
  - bootstrap indexing in an `initContainer`
  - ongoing repo sync and re-index in the sidecar
- The public HTTP API is intentionally read/query focused. It does not expose a mutable watch/jobs control plane.

## Submitting Changes

1. Make the smallest coherent change that solves the problem.
2. Run the relevant tests and guards locally.
3. Update docs when the public behavior or package layout changes.
4. Open a pull request against `main` with a concise explanation of the change.
