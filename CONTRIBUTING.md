# Contributing to PlatformContextGraph

Contributions are welcome. Small, well-scoped pull requests are preferred over broad refactors.

## Guidelines

- Keep pull requests focused on a single problem or feature.
- Match the existing code style and structure.
- Add or update tests when behavior changes.
- Keep handwritten Python modules under `src/` at 500 lines or fewer.
- Add Google-style docstrings for handwritten Python modules, classes, methods, and functions under `src/`.
- Call out follow-up work separately instead of bundling unrelated cleanup.

## Development Setup

1. Fork the repository.
2. Install the development environment:

```bash
uv sync
```

3. Create a branch for your work:

```bash
git checkout -b feature/my-change
```

## Running Checks

Before opening a pull request:

```bash
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
uv run black --check src tests
./tests/run_tests.sh fast
```

See [TESTING.md](TESTING.md) for the full test strategy and layer breakdown.

## Submitting Changes

1. Make the smallest change that solves the problem.
2. Run the checks above locally.
3. Commit with a clear message.
4. Open a pull request against `main`.

## Maintainer

PlatformContextGraph is maintained by Allen Sanabria. GitHub: [@linuxdynasty](https://github.com/linuxdynasty)
