# React and Next.js Semantic Pack Design

## Problem

PCG now has first-class TSX parsing, but frontend repos still lose important
framework meaning after syntax parsing succeeds. In practice that means PCG can
parse a file correctly while still failing to answer questions like:

- is this module a client or server component?
- is this file a Next.js page, layout, or route handler?
- does this module provide metadata or API verbs?
- is this file an interactive React component or only a server-rendered shell?

Those gaps matter because operators and AI users ask product and deployment
questions in framework terms, not only in AST terms.

## Grounding Evidence

The need is visible in local repos that PCG already indexes.

### Next.js app router examples

- [page.tsx](/Users/allen/repos/services/portal-nextjs-platform/apps/portal-platform-web/src/app/[locale]/(boats)/bdp/[boatSlug]/page.tsx)
  - server component
  - exports `generateMetadata`
  - exports default async page component
- [route.ts](/Users/allen/repos/services/portal-nextjs-platform/apps/portal-platform-web/src/app/api/msw/status/route.ts)
  - imports `NextResponse`
  - exports `GET`
  - behaves like an API route handler
- [layout.tsx](/Users/allen/repos/services/webapp-node-fsbo/next-app/src/app/[site]/sell/layout.tsx)
  - exports default layout component
  - wraps child routes with shared UI

### React client component example

- [DocumentsPanel.tsx](/Users/allen/repos/services/portal-java-ycm/next/app/components/ui/Documents/panels/DocumentsPanel.tsx)
  - starts with `'use client'`
  - uses React state and interactive UI primitives
  - represents a clear client-only component boundary

These are normal patterns in production React and Next.js code. If PCG claims
support for those ecosystems, it should surface these semantics explicitly.

## Goals

- Add a thin, reliable semantic layer on top of JS/TS/TSX parsing for React and
  Next.js.
- Keep the first slice shallow enough to validate well on real repos.
- Emit framework facts that help support, dependency, and architecture
  questions without needing prompt engineering.
- Establish the contract that later JS/TS framework packs will follow.

## Non-Goals

- Full semantic understanding of every React pattern or Next.js feature.
- Exhaustive hook-flow analysis or JSX data-flow modeling.
- Framework-specific graph entities for every component instance in the first
  slice.
- Support for every Next.js convention from legacy `pages/` and app router in
  one pass.

## Design Principles

- Prefer high-signal module-level facts over speculative deep analysis.
- Use path conventions and explicit exports before fuzzy heuristics.
- Emit additive evidence; do not replace or distort existing parser output.
- Preserve low-cardinality facts that are easy to test and reason about.

## Proposed Support Contract

### React Base Pack

The first React semantic pack should detect:

- client component boundary via top-level `'use client'`
- server action or server boundary via top-level `'use server'`
- component module candidates via exported PascalCase function or variable
  component definitions
- hook usage via imports from `react` or local hooks matching `use[A-Z]...`

The first React pack should emit module-level facts such as:

- `framework = react`
- `react_boundary = client|server|shared`
- `react_component_exports = [...]`
- `react_hooks_used = [...]`

This first slice should not try to prove render trees or component nesting.

### Next.js Base Pack

The first Next.js semantic pack should detect app-router conventions through
path and export analysis:

- `app/**/page.{js,jsx,ts,tsx}`
- `app/**/layout.{js,jsx,ts,tsx}`
- `app/**/route.{js,jsx,ts,tsx}`
- metadata providers via:
  - `export const metadata`
  - `export async function generateMetadata`
- route handlers via exported HTTP verbs:
  - `GET`
  - `POST`
  - `PUT`
  - `PATCH`
  - `DELETE`
  - `HEAD`
  - `OPTIONS`
- request/response evidence via `NextRequest` and `NextResponse`

The first Next.js pack should emit module-level facts such as:

- `framework = nextjs`
- `next_module_kind = page|layout|route`
- `next_route_verbs = [...]`
- `next_metadata_exports = static|dynamic|both|none`
- `next_route_segments = [...]`
- `next_runtime_boundary = client|server`

### Shared Behavior

For modules that match both packs:

- Next.js facts should describe file role.
- React facts should describe runtime boundary and component behavior.
- Facts must coexist without overwriting one another.

## Where the Facts Should Live

The first slice should attach semantic facts to existing file/module parse
results rather than introducing a large new graph model immediately.

That gives us a low-risk path:

1. parse source with existing JS/TS/TSX frontends
2. run semantic recognizers over parsed file/module context
3. attach structured framework evidence to the parsed result
4. expose or project that evidence later into graph/query surfaces

This keeps the initial work incremental and testable.

## Acceptance Criteria

This slice is successful when:

1. PCG identifies `page`, `layout`, and `route` files correctly in app-router
   repos.
2. PCG distinguishes `'use client'` files from default server modules.
3. PCG captures metadata and HTTP verb exports without false positives from
   ordinary helper modules.
4. At least three real local repos pass framework-semantic smoke checks.
5. The emitted facts are bounded, low-cardinality, and suitable for later graph
   projection.

## Validation Targets

- `/Users/allen/repos/services/portal-nextjs-platform`
- `/Users/allen/repos/services/portal-java-ycm`
- `/Users/allen/repos/services/webapp-node-fsbo`

Expected evidence includes:

- app-router page/layout/route detection
- `'use client'` boundaries
- metadata export detection
- route handler verb detection

## Risks

- Overfitting to one repo’s folder layout or naming conventions.
- Treating any exported PascalCase symbol as a React component when it is not.
- Mixing runtime-boundary facts with component-classification facts too early.
- Adding facts that are so detailed they become hard to validate or index.

## Recommendation

Implement a combined **React + Next.js base pack** as the next maturity slice:

- React provides boundary and component semantics.
- Next.js provides app-router module-role semantics.
- Both stay intentionally shallow in the first iteration.

This is the best next step because it converts the TSX parser win into
framework-aware behavior that users can actually feel in answers.
