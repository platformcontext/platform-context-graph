# Parser Maturity Implementation Plan

## Outcome

Turn parser support into an explicit maturity program so PCG can honestly claim
support for languages and their popular frameworks at a higher quality bar.

## This Branch

This branch is the TSX promotion slice and the seed of the larger program.

Deliverables on this branch:

1. true `tsx` grammar routing
2. TSX junk-node regression protection
3. destructured typed prop normalization
4. real-repo validation against local TSX-heavy repos
5. PRD/roadmap for broader language and framework support
6. declarative React/Next.js framework-pack specs and loader
7. declarative Node HTTP framework packs for JavaScript and TypeScript
8. declarative Python web framework packs for FastAPI and Flask
9. declarative provider packs for bounded AWS and GCP JS/TS SDK evidence
10. graph-backed Python end-to-end validation through the shared support validator

## Next Slices

### Slice 1: Finalize TSX Promotion

Acceptance:

- parser unit suite green
- registry routing tests green
- real local TSX repos have no bogus `if` functions
- real local TSX repos have no oversized parameter blobs

Validation targets:

- `boats-chatgpt-app`
- `portal-nextjs-platform`
- `portal-java-ycm`
- `webapp-node-fsbo`

### Slice 2: JavaScript Framework Packs

Targets:

- React component conventions
- Node routing frameworks
- Next.js/Remix conventions where they overlap JS code paths

Acceptance:

- new semantic fixtures
- real repo validation on at least three repos

### Slice 3: TypeScript Framework Packs

Targets:

- typed route handlers
- generic components
- typed API clients
- typed service/config builders

Acceptance:

- normalized graph entities remain bounded and stable
- framework evidence is additive and not lossy

### Slice 4: SDK/Provider Packs

Targets:

- AWS JS/TS SDK
- GCP JS/TS clients

Model:

- declarative framework/provider specs for imports, constructors, calls, and
  semantic evidence built on the same pack-loading pattern now used for the
  React/Next.js lane

Acceptance:

- code evidence can produce higher-level dependency facts
- schema overlays do not replace syntax parsing

### Slice 5: Cross-Language Support Matrix

Add a support matrix in docs covering:

- language grammar status
- normalization status
- framework-pack status
- real-repo validation status

## Acceptance Bar For "Official Support"

We should not say a language/framework is fully supported until:

1. grammar routing is correct
2. core normalization is stable
3. regression fixtures exist for known bad patterns
4. at least three real repos pass parser smoke checks
5. one end-to-end indexing run passes on a substantial repo

## Validation Command Pattern

Use the repo’s real discovery path plus parser smoke checks:

```bash
PYTHONPATH=src uv run python -m pytest tests/unit/parsers/test_typescriptjsx_parser.py tests/unit/parsers/test_typescript_parser.py tests/unit/tools/test_graph_builder_parsers.py -q
```

And use the graph-backed validation script for end-to-end support checks:

```bash
PYTHONPATH=src uv run python scripts/validate_language_support_e2e.py \
  --repo-path /Users/allen/repos/services/portal-react-platform \
  --language javascript \
  --check \
  --require-framework-evidence
```

And real repo validation scripts that:

- honor discovery rules
- honor repo-local `.gitignore`
- honor `.pcgignore` if present
- report bogus function names
- report oversized normalized parameters

## Completed On This Branch

1. End-to-end indexing validation now passes on `/Users/allen/repos/services/portal-nextjs-platform`.
   - local run: `01e7ca696a30df95`
   - result: `1 completed / 0 failed / 0 pending`
   - repo context, repo summary, and repo story all surface React/Next.js framework evidence
2. End-to-end indexing validation now passes on `/Users/allen/repos/services/portal-react-platform`.
   - local run: `773c75cb105c8879`
   - result: `1 completed / 0 failed / 0 pending`
   - repo context, repo summary, and repo story all surface React framework evidence for the JavaScript lane
3. End-to-end indexing validation now passes on `/Users/allen/repos/services/api-node-platform`.
   - local run: `ef02081cb9874275`
   - result: `1 completed / 0 failed / 0 pending`
   - repo context, repo summary, and repo story all return successfully for the plain TypeScript lane on a zero-TSX repo
4. A reusable graph-backed validation script now exists at `scripts/validate_language_support_e2e.py`.
5. React/Next.js semantic packs are implemented through parser facts, file persistence, and query/story surfacing.
6. Public support-maturity docs are published and generated from specs.
7. React/Next.js semantic detection is now driven by declarative framework-pack YAML specs under `src/platform_context_graph/parsers/framework_packs/specs/`.
8. Node HTTP semantic detection is now driven by declarative Express and Hapi framework-pack YAML with repo/story/investigation surfacing.
9. Python web semantic detection is now driven by declarative FastAPI and Flask framework-pack YAML with repo/story/investigation surfacing.
10. JS/TS provider semantic detection now emits bounded AWS and GCP SDK evidence at file, repo summary, story, and investigation layers.
11. The graph-backed support validator now supports Python and validated clean local runs for `recos-ranker-service` and `lambda-python-s3-proxy`.
12. Parser registry startup now degrades cleanly when an unrelated tree-sitter grammar bootstrap fails, instead of blocking indexing for every language.

## Open Follow-Ups

1. Extend provider packs beyond the current bounded AWS/GCP constructor evidence.
2. Add deeper framework lanes such as NestJS, Remix, or Django when strong local validation targets justify them.
3. Expand the same maturity program to additional language/framework pairs beyond the current JS/TS/TSX/Python lane.

## PR Packaging

When this branch is wrapped:

- include TSX routing and normalization changes
- include tests and real-repo validation summary
- include the design spec and implementation roadmap
- update the PR description with:
  - the parser bug fixed
  - the TSX promotion outcome
  - the real repo validation evidence
  - the broader parser maturity roadmap
