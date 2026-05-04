# AGENTS.md — internal/buildinfo guidance for LLM assistants

## Read first

1. `go/internal/buildinfo/README.md` — purpose, exported surface, invariants
2. `go/internal/buildinfo/buildinfo.go` — `Version` var and `AppVersion()`; the
   entire surface fits in one file
3. Dockerfile — how the release version is injected via `-ldflags`

## Invariants this package enforces

- **`Version` is write-once via `-ldflags`** — no code path should assign to
  `Version` at runtime. `buildinfo.go:6` declares it as a package-level `var`
  so the linker can override it; treating it as a mutable var at runtime
  creates divergence between the binary and its reported version.
- **`AppVersion()` falls back to `"dev"`** — `buildinfo.go:12` returns `"dev"`
  when `strings.TrimSpace(Version)` is empty. All callers must use
  `AppVersion()`, not `Version` directly, so whitespace-only ldflags overrides
  are handled uniformly.

## Common changes and how to scope them

- **Change the default fallback string** — change the literal `"dev"` at
  `buildinfo.go:13`. Then update every status test and MCP server test that
  asserts on the default version string.

- **Add a second version attribute (e.g., git commit SHA)** — add a second
  `var` and a second accessor following the same ldflags pattern. Do not embed
  the SHA into `Version`; keep them separate so operators can query each
  independently.

## Failure modes and how to debug

- Symptom: `AppVersion()` always returns `"dev"` in production images →
  cause: `-ldflags` path mismatch — the import path passed to `-X` must
  exactly match `github.com/platformcontext/platform-context-graph/go/internal/buildinfo.Version`
  → fix: verify the `go build -ldflags` invocation in the Dockerfile.

- Symptom: version string contains leading or trailing whitespace in the
  status response → cause: caller reading `Version` directly instead of
  `AppVersion()` → fix: replace `buildinfo.Version` with `buildinfo.AppVersion()`.

## Anti-patterns specific to this package

- **Reading `Version` directly** — always use `AppVersion()` to get the
  normalized string.
- **Adding a version constant anywhere else** — the whole point of this
  package is that there is exactly one place. Adding a duplicate constant
  creates version drift.
