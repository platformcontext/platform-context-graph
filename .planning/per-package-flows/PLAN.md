# Plan: Per-Package Flow Documentation (READMEs + AGENTS.md + Mermaid)

## Why this exists

The READMEs we shipped in PR #139 are too light. The example the user
flagged (`go/internal/projector/README.md`) tells a contributor what the
package owns but not how it works — no flow, no lifecycle, no place to start
reading. Open-source contributors and LLM assistants both bounce off it.

The user's correction:

> Each README should explain how that portion works and the flow. Use mermaid
> diagrams. Add an accompanying AGENTS.md per package so an LLM understands
> the flow and makes best-in-class choices.

This plan delivers that, with explicit slop-prevention so we don't repeat
the previous round's invented-identifier problem (`GraphWrite`, `Server`,
`RuntimeAdminRequest`).

## What "rich" actually means per package

For tiered packages, each `README.md` gains these sections in this order:

1. **Purpose** (existing — kept).
2. **Where this fits in the pipeline** — one mermaid `flowchart LR` showing
   this package's neighbors in the canonical pipeline (`sync → discover →
   parse → emit facts → enqueue → reduce → graph/content → query`).
3. **Internal flow** — one mermaid `flowchart TB` (or `stateDiagram-v2` if
   the code has an enum-driven state machine) showing the package's own
   stages, claim/lease cycle, or request handling. Every node names a real
   exported function or type from the package — verified by the harness.
4. **Lifecycle / workflow** — prose walking through one full pass: what
   triggers the work, what state it reads, what it writes, what acks or
   advances.
5. **Exported surface** (existing — kept).
6. **Dependencies** (existing — kept).
7. **Telemetry** (existing — kept).
8. **Operational notes** — runbook-style: how an operator at 3 AM diagnoses
   "is it stuck / slow / failing / OOM / done?" using the metrics, spans,
   and admin endpoints this package emits.
9. **Extension points** — for contributors: what seams are open
   (interfaces, options, registries) and what is intentionally closed.
10. **Gotchas / invariants** (existing — kept).
11. **Related docs** (existing — kept).

Each tiered package also gets a per-package `AGENTS.md` for LLM assistants:

- **Read first** — ordered list of files to load when starting work here.
- **Invariants this package enforces** — claims about graph truth,
  ordering, idempotency, transaction scope. Each invariant must cite the
  file:line where the code enforces it.
- **Common changes and how to scope them** — e.g. "adding a new fact type"
  → list of files to touch; "adding a new telemetry attribute" → file +
  CLAUDE.md rule reference.
- **Failure modes and how to debug** — symptom → likely cause → which
  metric / log key to check first.
- **Anti-patterns specific to this package** — past bugs preserved as
  warnings.
- **What NOT to change without an ADR** — closed seams.

`doc.go` is unchanged where accurate; refreshed where the previous round
named identifiers that don't exist (already mostly fixed in PR #139's
follow-up commit).

## Slop prevention — the harness

The previous round shipped invented identifiers. This round runs a
verification gate on every package before commit.

### Step 1 — Per-package research artifact

Each agent's first job is to produce a structured fact sheet, not prose.
The agent writes `.planning/per-package-flows/research/<pkg>.json` with:

```json
{
  "package": "internal/projector",
  "package_name_decl": "projector",
  "exported_types":   [{"name":"...","file":"...","line":42}],
  "exported_funcs":   [{"name":"...","file":"...","line":17}],
  "exported_consts":  [...],
  "exported_vars":    [...],
  "internal_imports": ["github.com/.../internal/facts", ...],
  "external_imports": ["github.com/jackc/pgx/v5", ...],
  "telemetry": {
    "spans":   ["telemetry.SpanProjectorRun", ...],
    "metrics": ["pcg_dp_projector_*"],
    "log_keys": ["telemetry.LogKeyDomain", ...]
  },
  "env_vars":         [{"name":"PCG_PROJECTOR_BATCH","file":"...","line":12}],
  "state_machines":   [{"type":"Stage","values":["...","..."],"file":"..."}],
  "error_types":      ["..."],
  "test_files":       ["..."],
  "adr_references":   ["docs/docs/adrs/2026-04-22-...md"],
  "fixture_intent":   "..."
}
```

Each entry includes `file` and `line` so the writing phase can cite it.
The fact sheet is committed alongside the README to the planning dir;
reviewers can spot-check claims.

### Step 2 — Constrained writing

The writing phase is given the fact sheet and forbidden from inventing
identifiers. Specific rules:

- **Every backticked Go identifier in `README.md` and `AGENTS.md` must
  appear in `exported_types ∪ exported_funcs ∪ exported_consts ∪
  exported_vars ∪ telemetry.* ∪ env_vars ∪ state_machines.values`** OR be
  a Go-language built-in (`chan`, `map`, `string`) OR a stdlib name
  (`http.Handler`, `context.Context`).
- **Every mermaid node label that looks like a Go identifier must obey
  the same rule.**
- **Anti-marketing pass**: forbid `leverages, seamlessly, robust, powerful,
  comprehensive, key role, stands as, serves as, underscores, showcases,
  facilitates`. Run `rg -i` over the draft and remove hits.
- **No claims about behavior that doesn't appear in source.** If the agent
  wants to write "retries on conflict" the fact sheet must show retry
  logic in a real file:line.

### Step 3 — Automated verifier

A script at `scripts/verify-doc-claims.sh <pkg-dir>` runs after the agent
finishes:

1. Extracts every backticked CamelCase token from `README.md` and
   `AGENTS.md`.
2. For each, confirms it appears literally in at least one `.go` file in
   the package directory OR in `internal/telemetry/` (for telemetry
   names) OR in the import block (for stdlib types).
3. Reports unverifiable tokens. The agent must remove them or replace
   with a real identifier before commit.
4. The script also runs the anti-marketing `rg -i` and fails on hits.

This is the gate that runs in CI shape locally. The parent (me) runs it
on every package before approving — not the agent's self-report.

### Step 4 — Parent verification

After each agent finishes its package, I:

1. Read the produced README.md, AGENTS.md, and the research JSON.
2. Run `verify-doc-claims.sh <pkg>` and confirm clean.
3. Read the actual source for one randomly-picked claim and confirm.
4. Run `go vet ./...` to catch any doc.go-level breakage.
5. Check that the mermaid diagrams render — pass through a
   github.com-style mermaid validator (or `mermaid-cli` locally if
   installed).

If any check fails, I push back to the agent or fix manually.

## Pilot first: projector

The user's example is `internal/projector`. That makes it the obvious
pilot — we know what "too light" looks like for that package, so we
have a clear bar.

Pilot sequence:

1. Build the verifier script `scripts/verify-doc-claims.sh`.
2. Run one Sonnet agent on `internal/projector` with the calibrated
   contract above. Agent produces fact sheet + README + AGENTS.md.
3. I verify with the harness.
4. Show output to the user. They review. Iterate on the prompt or
   structure if needed.
5. Once the projector output is approved, lock the prompt template and
   roll out to the other Tier 1 packages in parallel.

## Tiering

### Tier 1 — high-priority services (13 packages)

The packages a contributor is most likely to land in first. These get the
full treatment: rich README + per-package AGENTS.md + mermaid flows +
research JSON.

**Binaries (7):**
- `go/cmd/ingester`
- `go/cmd/reducer`
- `go/cmd/api`
- `go/cmd/mcp-server`
- `go/cmd/bootstrap-index`
- `go/cmd/projector`
- `go/cmd/workflow-coordinator`

**Pipeline-owning internal packages (6):**
- `go/internal/collector` (git collection + discovery owner)
- `go/internal/parser` (parser registry + language adapters)
- `go/internal/projector` (source-local projection) ← pilot
- `go/internal/reducer` (cross-domain materialization)
- `go/internal/query` (HTTP API surface)
- `go/internal/mcp` (MCP tool implementations)

### Tier 2 — supporting packages (10 packages)

Get rich README extension and a per-package AGENTS.md, but mermaid is
optional (only if the package has real internal state worth diagramming).

- `go/internal/coordinator`
- `go/internal/runtime`
- `go/internal/storage/postgres`
- `go/internal/storage/cypher`
- `go/internal/relationships`
- `go/internal/correlation` + `correlation/{engine,rules,admission,model,explain}`
- `go/internal/recovery`
- `go/internal/status`
- `go/internal/telemetry`
- `go/internal/workflow`

### Tier 3 — leaf utilities (the rest, ~25 packages)

Keep current README + doc.go. Add only a small "How this fits" pointer at
the top of each so a reader landing here knows where to go for the
pipeline-level view.

Examples: `buildinfo`, `repositoryidentity`, `scope`, `contentrefs`,
`app`, `truth`, `queue`, `facts`, `graph`, `iacreachability`,
`pcglocal`, `terraformschema`, `terraformschema/schemas`,
`content`, `content/shape`, `collector/discovery`,
`storage/neo4j`, `reducer/{aws,dsl,tags,tfstate}`.

## Execution waves

1. **Wave 0**: Build the verifier script + the calibrated agent prompt
   template. Pilot on `internal/projector`. User review.
2. **Wave 1**: Tier 1 internal packages (5 remaining: collector, parser,
   reducer, query, mcp) — 5 parallel Sonnet agents.
3. **Wave 2**: Tier 1 binaries (7 packages) — 7 parallel Sonnet agents.
4. **Wave 3**: Tier 2 supporting packages (10 packages) — split into
   2 batches of 5 to keep agent throughput sane.
5. **Wave 4**: Tier 3 light additions (one agent does all 25 in one pass —
   each gets a single-paragraph "How this fits" pointer, low risk).
6. **Wave 5**: Update root `CLAUDE.md` and `AGENTS.md` to point at the
   new per-package layout. Ensure lockstep. Ensure
   `TestRepositoryDocumentationStandardsAreEnforced` still passes.
7. **Wave 6**: Verification — `go vet`, `go test ./internal/runtime`,
   `mkdocs --strict`, `git diff --check`,
   `scripts/check-docs-stale.sh --all` (zero drift),
   `scripts/verify-doc-claims.sh` across all tiered packages.
8. **Wave 7**: Commit per ownership domain (multiple atomic commits),
   push, open PR.

## Open questions for the user

Before Wave 0 starts I need confirmation on:

- Are the Tier 1 / Tier 2 / Tier 3 splits correct? In particular, should
  `internal/coordinator` and `internal/runtime` be Tier 1 (most binaries
  depend on them) instead of Tier 2?
- For Tier 3 packages, is a single-paragraph "How this fits" addition
  enough, or do you want them all to get mermaid + AGENTS.md too?
- Should `AGENTS.md` per package get a CLAUDE.md mirror per package
  (lockstep at the package level), or is the lockstep rule only for the
  root files?
- How should I handle commit granularity — one commit per Tier 1 package
  (~13 commits), or one commit per wave (~7 commits), or one bulk commit
  at the end?

Once those are answered, Wave 0 starts on `internal/projector` and you
review the output before I parallelize.
