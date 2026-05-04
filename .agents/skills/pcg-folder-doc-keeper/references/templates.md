# Templates and worked examples

## README.md template

```markdown
# <Package Title>

## Purpose

<One paragraph. What this package owns and why it exists.>

## Ownership boundary

<What this package owns, and what it explicitly does not.>

## Exported surface

- `<TypeOrFunc>` — <one-line role>
- ...

See `doc.go` for the full godoc contract.

## Dependencies

- `<go/internal/...>` — <why this package depends on it>
- ...

## Telemetry

- Metrics: `pcg_dp_<name>_*` — <when emitted>
- Spans: `<SpanName>` — <when started>
- Logs: scope `<scope>`, phase `<phase>`

## Gotchas / invariants

- <one bullet per non-obvious rule>

## Related docs

- `docs/docs/<page>.md`
- ADR: `docs/docs/adrs/<file>.md`
```

## doc.go template

```go
// Package <name> <one-sentence summary>.
//
// <Contract: guarantees, failure modes, invariants. Reference the spec, ADR,
// or behavior contract this package implements.>
package <name>
```

## Worked example 1 — go/internal/runtime

`runtime` is a shared-process utility package. The README focuses on which
binaries depend on it; the doc.go states the runtime contract.

`README.md`:

```markdown
# Runtime

## Purpose

The runtime package owns shared process wiring: admin muxes, health and
status handlers, datastore configuration, retry policy, memory limits, API
key resolution, and Compose/runtime contract tests.

## Ownership boundary

Process-level wiring used by every PCG binary. Does not own domain logic
(facts, queue, projection) — those have their own packages.

## Exported surface

- `Server` — admin HTTP surface
- `RetryPolicy` — default backoff and jitter
- `DataStore` — datastore configuration loader

See `doc.go` for the full contract.

## Dependencies

- `internal/telemetry` — span and metric helpers
- `internal/status` — health/readiness probes

## Telemetry

- Metrics: `pcg_dp_runtime_*`
- Spans: `RuntimeAdminRequest`
- Logs: scope `runtime`

## Gotchas / invariants

- Changes here usually affect more than one binary. Update local testing
  docs, Compose docs, Helm docs, or runtime admin docs when the process
  contract changes.
- Admin endpoints must remain non-authenticated only on the admin port.

## Related docs

- `docs/docs/deployment/service-runtimes.md`
- `docs/docs/reference/local-testing.md`
```

`doc.go`:

```go
// Package runtime provides shared process runtime contracts for PCG services.
//
// The package owns admin HTTP surfaces, metrics endpoints, lifecycle wiring,
// retry policy defaults, API key checks, and data-store configuration shared by
// the API, MCP, ingester, reducer, and helper binaries.
package runtime
```

## Worked example 2 — go/internal/storage/cypher

`storage/cypher` is a backend-neutral seam. The README documents the seam
intent; doc.go states what callers can rely on.

`README.md`:

```markdown
# Cypher Storage

## Purpose

`storage/cypher` owns backend-neutral graph write contracts, canonical
writers, edge helpers, statement metadata, and write instrumentation.

## Ownership boundary

Backend-neutral. Dialect-specific behavior belongs in
`storage/neo4j` or the NornicDB adapter, not here.

## Exported surface

- `GraphWrite` — port implemented by every backend
- `Statement` — typed Cypher write with metadata
- canonical writers for nodes, edges, properties

See `doc.go` for the contract.

## Dependencies

- `internal/telemetry` — write instrumentation
- consumers in `internal/projector`, `internal/reducer`

## Telemetry

- Metrics: `pcg_dp_cypher_write_duration_seconds`,
  `pcg_dp_cypher_write_errors_total`
- Spans: `CypherWrite`

## Gotchas / invariants

- Do not spread `neo4j` or `nornicdb` conditionals through caller packages.
  When backends differ, add the seam here as a schema adapter, writer
  option, or query builder.
- Canonical writers must remain idempotent; reducers retry on conflict.

## Related docs

- `docs/docs/architecture.md` (graph backend section)
- `docs/docs/adrs/2026-04-22-nornicdb-graph-backend-candidate.md`
```

`doc.go`:

```go
// Package cypher defines the backend-neutral Cypher write contract for PCG.
//
// The package exposes GraphWrite, canonical statement builders, edge helpers,
// and write instrumentation. Backend dialects (Neo4j, NornicDB) implement
// this contract behind documented narrow seams; callers depend on this
// package, not on a concrete backend.
package cypher
```

## Worked example 3 — a leaf package (correlation/explain)

Smaller packages still get both files. Keep sections short rather than
omitting them.

`README.md`:

```markdown
# Correlation Explain

## Purpose

Renders correlation decisions into human-readable explanations consumed by
the explain API and the MCP server.

## Ownership boundary

Read-only formatter. Does not run correlation rules — that lives in
`correlation/engine`.

## Exported surface

- `Render(decision Decision) Explanation` — produce a structured
  explanation from an admission decision

See `doc.go` for the contract.

## Dependencies

- `internal/correlation/model` — decision shape
- `internal/truth` — canonical truth references

## Telemetry

None. Explanations are produced inline with the calling request and
inherit its span.

## Gotchas / invariants

- Explanations must reference the same evidence the engine considered, in
  the same order. Out-of-order rendering misleads operators.

## Related docs

- `docs/docs/reference/http-api.md` (explain endpoint)
```

`doc.go`:

```go
// Package explain renders correlation admission decisions into structured
// explanations for the explain API and MCP consumers.
//
// Each explanation lists the evidence the engine considered in the order it
// was applied, so operators can replay the decision against fixtures.
package explain
```

## Anti-patterns to reject

- README that is just an alphabetized list of file names. Files change; the
  list rots. Describe the surface, not the directory listing.
- doc.go whose comment is "// Package x." with nothing else.
- README and doc.go that both contain the same paragraph. Link, don't
  duplicate.
- README that lists every exported identifier with one-line repeats of the
  godoc comment. The README is for context that godoc cannot carry.
- "Robust," "powerful," "comprehensive," "robust solution." Cut every one.
