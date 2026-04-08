# Parser Maturity Design

## Problem

PCG supports many languages, but support quality varies. A language can be
"supported" in the extension registry while still missing one or more of the
things users actually care about:

- correct grammar selection
- normalized AST output for common coding patterns
- framework-aware semantic extraction
- confidence that real repos parse without pathological output

The TSX work on this branch exposed that gap clearly. `.tsx` was present in the
registry, but it was not truly first-class until we added:

- real `tsx` grammar routing
- protection against recovered junk nodes
- normalization for destructured typed component props
- validation against real local repos

We want that same grade of support for every language we claim to support and
for the popular frameworks within those ecosystems.

## Goals

- Define what "supported" means for a language in PCG.
- Define how framework-level semantics should be layered on top of syntax
  parsing.
- Reuse schema-driven techniques where they fit, similar to Terraform provider
  evidence, without confusing schema overlays with language parsing.
- Establish validation gates using real local repositories, not only synthetic
  fixtures.

## Non-Goals

- Implement full framework support for every language in one branch.
- Replace tree-sitter with compiler-specific frontends everywhere.
- Guarantee perfect semantic understanding of every library or DSL.

## Support Model

### Layer 1: Grammar Correctness

Each file type must route to the correct grammar, not a nearby approximation.

Examples:

- `.ts` -> `typescript`
- `.tsx` -> `tsx`
- `.jsx` -> JavaScript grammar with JSX support if available

Acceptance criteria:

- the language manager knows the canonical language name
- the registry routes each extension correctly
- grammar-specific tests prove the route is active

### Layer 2: AST Normalization

Raw AST nodes must be normalized into stable graph-friendly entities.

Examples:

- destructured typed component props become bound names, not one raw blob
- recovered syntax junk is filtered instead of indexed
- class methods, object literal methods, and component functions are preserved

Acceptance criteria:

- parameter names remain stable and bounded
- no bogus functions from error recovery
- representative real-code patterns have regression tests

### Layer 3: Framework Semantic Packs

Once syntax parsing is correct, framework semantics should be layered on top as
data-driven recognizers where possible.

Examples:

- React component packs
- Next.js route/page/layout packs
- Remix loader/action packs
- Express/Fastify/Hapi route packs
- AWS SDK v3 usage packs
- GCP client usage packs

These packs are analogous to Terraform provider schemas in spirit, but not in
responsibility:

- grammar handles syntax
- normalization handles stable entities
- framework packs map code patterns to higher-level semantic facts

Framework packs should be declarative when practical:

- entity patterns
- call signatures
- import/module markers
- route conventions
- config file conventions
- semantic labels to emit

### Layer 4: Real-Repo Validation

Synthetic fixtures are necessary but insufficient. Every promoted language or
framework must be validated against local real-world repos.

Validation classes:

- parser-only fixtures
- focused regression corpus from real code
- repo-scale scans over real local repos
- end-to-end indexing checks on at least one substantial repo

## What "Supported" Means

PCG should only call a language/framework "supported" when it meets all of the
following:

1. Correct grammar routing is in place.
2. Common syntax patterns normalize into stable entities.
3. Known pathological parser outputs are blocked by regression tests.
4. At least three real repos from that ecosystem pass a parser-quality smoke
   check.
5. At least one repo has end-to-end indexing validation with acceptable graph
   output.

## Current Status

### JavaScript

- baseline parsing is established
- framework semantics are still uneven
- should be treated as syntax-supported, framework-maturing

### TypeScript

- baseline parsing is established
- framework semantics are still uneven
- should be treated as syntax-supported, framework-maturing

### TSX

This branch raises TSX to first-class parser support:

- correct `tsx` grammar routing
- recovered junk filtering
- destructured typed prop normalization
- validation against:
  - `boats-chatgpt-app`
  - `portal-nextjs-platform`
  - `portal-java-ycm`
  - `webapp-node-fsbo`

## Framework Pack Strategy

We should add framework packs incrementally, prioritizing ecosystems that appear
often in local repos and materially improve deployment, network, or dependency
reasoning.

Suggested initial packs:

1. React component and hook pack
2. Next.js app/router pack
3. Node service route pack
4. AWS JS/TS SDK pack
5. GCP JS/TS client pack

Each pack should define:

- trigger imports/modules
- relevant file path conventions
- semantic entities or evidence to emit
- acceptance fixtures
- real repo validation targets

## Risks

- Over-normalization can lose useful detail.
- Framework packs can become brittle if they are too library-version specific.
- Broad claims of support without real-repo validation will keep hurting trust.

## Recommendation

Adopt a parser maturity program with explicit support levels:

- syntax supported
- normalized supported
- framework-aware supported
- production-validated supported

TSX should be the template for how we promote the next language or framework
slice.
