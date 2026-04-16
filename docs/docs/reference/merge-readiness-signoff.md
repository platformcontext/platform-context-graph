# Merge Readiness Signoff

This page is the final signoff record for the
`codex/go-data-plane-architecture` branch.

Use it to answer one practical question:

- what is fully closed for the Python-to-Go migration
- what is intentionally still present, but only as fixture or offline tooling
- what was explicitly deferred instead of silently left unfinished

## Closed

These migration goals are complete on this branch:

- all deployed and long-running runtime ownership is Go-owned
- Dockerfile, Compose, and Helm run the Go platform
- API, MCP, ingester, bootstrap, reducer, projector, admin/status, and recovery
  paths are Go-owned
- no `src/` Python runtime tree remains
- no normal-path Python bridge or runtime ownership remains
- no active Python command invocations remain in normal developer verification
  scripts
- no checked-in `.py` files remain outside `tests/fixtures/`
- runtime-ownership rows in the parity audit and closure matrix are marked
  `pass` or intentionally `bounded`

## Intentionally Fixture-Only

These Python files remain on purpose:

- `tests/fixtures/**`

They are parser and query-surface fixture inputs, not runtime code.

They remain in Python because the Go parser must still prove Python-language
support against realistic source examples.

## Intentionally Offline-Only

These Python-dependent surfaces remain outside normal runtime and developer-path
ownership:

- MkDocs configuration and docs build workflows
- GitHub Actions that install Python only for docs or bundle-generation tasks

They do not participate in deployed service ownership or normal local runtime
verification.

## Explicitly Deferred

These items were not expanded into this migration:

- standalone auth service or gateway-only auth layer
- user management
- OAuth or OIDC product flows
- multi-tenant authorization design

Those decisions were deferred intentionally and recorded in:

- [Auth Boundary And Deferred User Management](../adrs/2026-04-16-auth-boundary-and-deferred-user-management.md)

## Not In Scope For This Migration

These are not migration blockers:

- converting fixture source files away from Python
- removing Python from MkDocs itself
- removing Python from every CI workflow regardless of purpose
- net-new parser behavior beyond the bounded non-goals already documented in
  the parity audit

## Final Branch Truth

The honest branch-level statement is:

- runtime and service migration is complete
- active developer-path migration is complete
- remaining Python is fixture-only or offline-only
- feature-for-feature parity is not yet fully signed off because queue
  hardening, typed relationship fidelity, and several workflow/IaC
  relationship families still need implementation and proof

## Verification Snapshot

Use this record only when the open parity rows are actually closed. The current
readiness gate still depends on:

- projector/reducer queue-hardening proof
- typed relationship fidelity proof
- GitHub Actions, Terraform variable-file, Jenkins/Groovy, Ansible, Docker,
  and Docker Compose relationship proof
- docs, telemetry, and compose-backed evidence refresh

At final signoff time, the branch truth should be supported by:

```bash
rg --files . -g '*.py' | rg -v '^(\\./)?tests/fixtures/'
rg -n "python3 -c|uv run python|python -m|PYTHONPATH=src|platform_context_graph\\.core" scripts tests docs -g '!docs/site/**' -g '!tests/fixtures/**'
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
git diff --check
```

The first two commands should return no active runtime or developer-path Python
ownership.

## Companion Records

- [Python-To-Go Parity Audit](python-to-go-parity.md)
- [Parity Closure Matrix](parity-closure-matrix.md)
