"""Implementation plan for parser and framework maturity."""

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
  semantic evidence

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

And real repo validation scripts that:

- honor discovery rules
- honor repo-local `.gitignore`
- honor `.pcgignore` if present
- report bogus function names
- report oversized normalized parameters

## Open Follow-Ups

1. Add end-to-end indexing validation for a large TSX-heavy repo.
2. Add framework semantic packs for React and Next.js.
3. Design a declarative framework/provider pack format.
4. Publish a support matrix in public docs.

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
