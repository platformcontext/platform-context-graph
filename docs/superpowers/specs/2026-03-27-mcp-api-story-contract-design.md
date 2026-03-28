# MCP/API Story And Programming Prompt Contract

## Summary

This PRD defines one prompt contract with two lanes:

- `story` lane: end-to-end repository, workload, and service narratives that
  answer "Internet to cloud to code" questions with structured evidence
- `programming` lane: code-centric query behavior for search, callers, callees,
  hierarchies, methods, imports, complexity, and dead code

This document extends, and does not replace, the shared-query umbrella in
[2026-03-19-query-model-api-design.md](2026-03-19-query-model-api-design.md).
That umbrella defines the shared query layer; this PRD defines the user-facing
contract that MCP and HTTP must expose on top of it.

## Product Direction

PlatformContextGraph should answer questions as a story, not as a bag of raw
tool outputs. A caller asking about `api-node-boats` should not need to know in
advance whether the answer requires repository context, workload context,
deployment traces, content lookups, Terraform relationships, or ArgoCD
resources. PCG should assemble that narrative, expose the supporting evidence,
and be truthful about what is missing.

At the same time, programming prompts should stay crisp and tool-like. The
product should not force code search, caller analysis, or complexity lookup
through a second narrative layer when the existing code-query surfaces are the
right contract. Instead, the programming lane standardizes those surfaces across
MCP and HTTP.

## Goals

- define one PRD with two lanes instead of separate PRDs
- make `structured story + evidence` the primary story-lane contract
- add top-level story surfaces for repositories, workloads, and services
- keep existing context and lower-level query tools as drill-down evidence
  surfaces
- normalize programming-lane public behavior around canonical `repo_id`
- make prompt suites a permanent part of integration and e2e testing
- keep MCP conversational and HTTP resource-oriented without letting them drift

## Non-Goals

- replacing the shared query layer
- forcing every code query into a narrative response
- exposing server-local checkout paths as a normal part of story answers
- allowing prompt acceptance to fall back to raw Cypher or server filesystem
  reads
- solving every currently unsupported code query pattern in this slice

## Shared Contract Principles

### Truthfulness

- Every answer must be explicit about incompleteness.
- Missing evidence must produce a limitation signal, not a silent omission.
- Story outputs must not imply that "not found in current evidence" means "does
  not exist."

### Portability

- Public file references should use `repo_id + relative_path`.
- Story answers must not rely on server-local filesystem paths.
- Prompt examples and prompt-suite tests must remain portable across local and
  hosted deployments.

### Evidence-first derivation

- Story summaries are derived from indexed graph/content evidence.
- Drill-downs should lead to the lower-level query surfaces that justify the
  summary.
- Raw Cypher remains an expert diagnostic path, not a normal prompt-coverage
  fallback.

## Lane 1: Story

### Story surfaces

The story lane adds new top-level surfaces and repositions existing ones:

- MCP:
  - `get_repo_story`
  - `get_workload_story`
  - `get_service_story`
- HTTP:
  - `GET /api/v0/repositories/{repo_id}/story`
  - `GET /api/v0/workloads/{workload_id}/story`
  - `GET /api/v0/services/{workload_id}/story`

Existing context and support tools remain valid, but they are no longer the
primary user-facing contract for "tell me the whole story" prompts.

### Story-lane input rules

- MCP story tools may accept plain names or slugs when the underlying shared
  query layer can resolve them safely.
- HTTP story routes stay canonical-ID based.
- Public HTTP examples must use `resolve` first when the caller starts with a
  fuzzy name or alias.

### Story response contract

Story responses should be structured around these keys:

- `subject`
- `story`
- `story_sections`
- `deployment_overview` or `code_overview`
- `evidence`
- `limitations`
- `coverage`
- `drilldowns`

The keys are intentionally stable and transport-neutral. The contract is that
the summary, evidence, and limitations all coexist in the same response.

### Story response semantics

- `subject`: canonical identity of the thing being described
- `story`: short narrative lines ordered by importance
- `story_sections`: grouped summary sections such as Internet, Deployment,
  Runtime, Dependencies, Resources, or Code
- `deployment_overview` / `code_overview`: structured facts supporting the
  narrative
- `evidence`: compact evidence entries that back the story
- `limitations`: explicit missing-domain or incomplete-coverage markers
- `coverage`: completeness metadata when available
- `drilldowns`: handles for the next structured query, not a prompt to inspect
  server-local paths

### Story-lane truth rules

- Story outputs must prefer indexed graph/content data over filesystem access.
- No story prompt acceptance path may require raw Cypher.
- No story prompt acceptance path may require server-local filesystem reads.
- If coverage is partial, the response must say so in `limitations` or
  `coverage`.

## Lane 2: Programming

### Programming surfaces

The programming lane keeps the existing code-query surfaces as the primary
contract:

- code search
- relationship analysis
- complexity analysis
- dead-code analysis

The goal is not to invent a second story tool for code, but to make the
existing surfaces consistent across MCP and HTTP.

### Programming-lane normalization rules

- canonical `repo_id` terminology everywhere public
- same default fuzzy/exact behavior across MCP and HTTP
- same limit defaults across MCP and HTTP
- same repo-relative result identity for drill-down workflows
- same error intent even when MCP and HTTP wrap failures differently

### Required programming-lane fixes in this slice

- fix the `module_deps` contract mismatch
- fix search-to-drill-down round trips so results feed content/context lookups
  without absolute server-local paths
- normalize dead-code scoping to public `repo_id`
- document unsupported prompt classes explicitly instead of leaving them
  ambiguous

### Unsupported or partial prompt classes

If a programming prompt is not publicly supported in this slice, the product
must either:

- promote it into the public contract and add coverage, or
- mark it as an expected failure in acceptance tests and docs

Ambiguity is not acceptable.

## Public Interface Contract

### MCP

- conversational ergonomics are allowed
- story tools may accept plain names/slugs
- code-query tools should still return canonical identities and repo-relative
  drill-down fields

### HTTP

- resource-oriented and canonical-ID based
- story entry for fuzzy names is `resolve` first, then call the canonical story
  route
- code-query bodies should use canonical `repo_id` when repository-scoped

## Testing Contract

Prompt suites are acceptance criteria, not just examples.

### Story lane

- all 20 approved story prompts must run against a known indexed ecosystem
  fixture
- MCP and HTTP should both expose the structured story contract where the
  transport supports it
- tests should assert required story structure, evidence presence, and
  limitation behavior
- prompt acceptance must not depend on filesystem reads or raw Cypher

### Programming lane

- all 16 programming prompts must run through both MCP and HTTP using one shared
  scenario table and thin transport adapters
- tests should assert canonical repo identity, repo-relative file identity, and
  round-trip drill-down compatibility
- parity tests should cover:
  - MCP vs HTTP default search behavior
  - `workspace` vs `ecosystem` scope equivalence
  - `module_deps`
  - repo identity normalization

### Docker-backed e2e

Keep a smaller Docker-backed e2e slice with at least:

- 5 story prompts
- 5 programming prompts

## Appendix A: Story Prompt Acceptance Suite

1. `What can you tell me about api-node-boats: API endpoints, DNS, AWS resources it depends on, what environments it is deployed to, what repos it depends on, and what Terraform or IaC repos are related to it? I want the end-to-end flow from Internet to cloud to code.`
2. `Show me the Internet-to-code request path for api-node-boats in QA, from DNS and gateway routing down to the service, container, and code entrypoints.`
3. `Where is api-node-boats deployed today, and how does QA differ from production in runtime, cluster, account, region, and deployment source?`
4. `What AWS resources does api-node-boats depend on, which ones are direct versus shared, and where in IaC are those dependencies declared?`
5. `Show me every public or internal hostname and API endpoint associated with api-node-boats, and tell me which repo and code path owns each one.`
6. `If api-node-boats is down in QA, walk me through the most likely failure points from DNS to gateway to workload to config to code.`
7. `If I change helm-charts for api-node-boats, what services, environments, and infrastructure components could be affected?`
8. `If I change api-node-boats itself, who consumes it directly or transitively, and what is the likely change surface?`
9. `Resolve repository:r_20871f7f to a repo name and explain what role that repo plays in the deployment or dependency chain for api-node-boats.`
10. `Which IaC repositories are related to api-node-boats, and what exactly does each one own: ArgoCD, Helm, Terraform, Crossplane, or cluster/platform setup?`
11. `Show me all environment overlays and config sources for api-node-boats, and infer whether each environment runs on EKS, ECS, or something else.`
12. `What AWS accounts, regions, clusters, and namespaces does api-node-boats run in, and what files prove that?`
13. `What secrets, SSM paths, IAM roles, or policy grants does api-node-boats rely on, and where are those permissions defined?`
14. `What container image does api-node-boats run, where is it built, how is it versioned, and what deploys that image into each environment?`
15. `Given the domain api-node-boats.qa.bgrp.io, what service owns it, how does traffic route, and what code repository is ultimately behind it?`
16. `Given this cloud resource or ARN, tell me which workload depends on it, what environment it belongs to, and which repos define or consume it.`
17. `Compare api-node-boats and api-node-boattrader: shared dependencies, shared infrastructure, shared IaC repos, and key deployment differences.`
18. `Create onboarding documentation for api-node-boats: what it does, how it is exposed, where it runs, what it depends on, who consumes it, and which repos matter.`
19. `Why is api-node-boats on EKS in QA but ECS in production, and what evidence supports that conclusion?`
20. `Show me the full deployment chain for api-node-boats, but keep it focused on only directly relevant repos, resources, and files instead of every shared module in the ecosystem.`

## Appendix B: Programming Prompt Acceptance Suite

1. `Where is process_payment defined?`
2. `Who calls process_payment?`
3. `What does process_payment call?`
4. `Find all indirect callers of normalize_config.`
5. `Find all indirect callees from handleRequest.`
6. `Find the call chain from main to process_payment.`
7. `Which files import requests?`
8. `Show the class hierarchy for Employee.`
9. `What methods does Employee have?`
10. `Find implementations of render.`
11. `Which functions take user_id?`
12. `Which functions are decorated with @app.route?`
13. `What is the complexity of process_payment in src/payments.py?`
14. `Show the most complex functions in payments-api.`
15. `Find dead code in this repo.`
16. `Where is API_KEY modified?`

## Appendix C: Known Current Gaps

- `module_deps` contract mismatch: addressed in this slice and kept as a
  regression target in parity tests.
- MCP/HTTP default-search drift: addressed in this slice and kept as a parity
  target in regression tests.
- `workspace` vs `ecosystem` scope equivalence: currently intentional and should
  be documented explicitly so callers do not assume different semantics where
  none exist yet.
- import-alias search, whole-repo class listing, and any other not-yet-promoted
  public programming prompt classes should be treated as expected failures until
  they are deliberately added to the contract.
