# React and Next.js Semantic Pack Implementation Plan

## Outcome

Add the first framework-aware semantic layer for JS/TS/TSX modules so PCG can
identify React boundaries and Next.js app-router roles in real repositories.

## Scope

This plan covers a thin base pack only:

- React client/server boundary detection
- React component export detection
- lightweight hook usage markers
- Next.js `page`, `layout`, and `route` detection
- Next.js metadata export detection
- Next.js route verb detection

This plan does not yet cover:

- deep component trees
- legacy `pages/` parity
- route parameter typing analysis
- server action call graphs
- framework-specific graph projection beyond bounded semantic facts

## Implementation Slices

### Slice 1: Semantic Pack Scaffolding

Add a lightweight semantic-pack layer for JS/TS/TSX parse results.

Deliverables:

- shared semantic fact model for framework evidence
- recognizer entrypoint for parsed modules
- tests proving facts are attached without changing core parser output

Acceptance:

- no regressions in JS/TS/TSX parser suites
- semantic facts are optional and additive
- file size and module boundaries stay within repo guardrails

### Slice 2: React Base Pack

Deliverables:

- detect top-level `'use client'`
- detect top-level `'use server'`
- detect exported component candidates
- detect hook usage markers

Acceptance:

- client modules are detected reliably in local repos
- server-marked modules are distinguished from client modules
- component export facts stay bounded and deterministic

### Slice 3: Next.js Base Pack

Deliverables:

- detect `app/**/page.*`
- detect `app/**/layout.*`
- detect `app/**/route.*`
- detect `metadata` and `generateMetadata`
- detect exported route verbs
- detect `NextRequest` and `NextResponse` usage

Acceptance:

- app-router roles are correct on representative local repos
- API route files surface HTTP verb facts
- metadata facts distinguish static and dynamic providers

### Slice 4: Real-Repo Validation

Run framework-semantic smoke checks against:

- `/Users/allen/repos/services/portal-nextjs-platform`
- `/Users/allen/repos/services/portal-java-ycm`
- `/Users/allen/repos/services/webapp-node-fsbo`

The validation should report:

- detected page/layout/route modules
- detected client/server boundaries
- metadata providers
- route handler verbs
- suspicious misses or false positives

Acceptance:

- three repos pass with stable counts
- validation honors discovery rules and ignore files
- no pathological output comparable to the old TSX regression

## Test Strategy

### Unit Fixtures

Add focused fixtures for:

- client component module
- server module
- page module with default export
- layout module with child wrapper
- route module with `GET` and `POST`
- page module with `generateMetadata`

### Repo-Driven Regression Coverage

Add compressed or reduced real-code fixtures derived from local repos when:

- a false positive is discovered
- a boundary is missed
- a metadata/route export is misclassified

### Verification

Minimum verification on this branch:

```bash
PYTHONPATH=src uv run --extra dev python -m pytest \
  tests/unit/parsers \
  tests/unit/tools/test_graph_builder_parsers.py -q
```

And real repo validation using discovery-aware smoke checks over the target
repos.

## Proposed File Boundaries

Keep the work split into small modules, for example:

- React recognizer
- Next.js recognizer
- shared semantic fact model
- shared validation helper

No single Python module should grow past the repo’s file-size limit.

## Documentation Updates

When implementation lands:

- update the parser maturity support matrix
- document React/Next.js support level as framework-aware
- include real repo validation evidence in the PR description

## Exit Criteria

This slice is ready for review when:

1. the semantic facts are implemented and tested
2. the local target repos validate cleanly
3. the docs describe what is and is not supported
4. the branch includes both design intent and implementation proof
