# Documentation Update Guide

This is a maintainer-only guide for updating the PlatformContextGraph docs site.

## Docs structure

PCG currently has **one** public documentation surface:

- `docs/mkdocs.yml` for site configuration and navigation
- `docs/docs/` for public docs content
- `docs/internal/` for maintainer-only notes
- `docs/archive/` for historical material that should not appear in the public site

## Public docs rules

- public markdown files live under `docs/docs/`
- public filenames use lower-case kebab-case
- public pages must be wired into `docs/mkdocs.yml`
- public docs should not reference removed frontend-hosting flows

## Editing flow

1. update or add Markdown under `docs/docs/`
2. update navigation in `docs/mkdocs.yml`
3. run the docs tests
4. build the site locally

## Local verification

```bash
cd docs
mkdocs serve
```

```bash
cd /Users/allen/personal-repos/platform-context-graph
PYTHONPATH=src uv run python -m pytest tests/integration/docs/test_docs_cleanup_contract.py tests/integration/docs/test_docs_smoke.py -q
```

## Build

```bash
cd /Users/allen/personal-repos/platform-context-graph
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
```
