# GitOps, Story, And Documentation Orchestration Design

## Summary

PlatformContextGraph already exposes strong graph-backed story surfaces and strong Postgres-backed content retrieval surfaces. The missing product layer is orchestration: deciding when a story answer needs raw content evidence and how to shape that combined evidence into documentation for a real audience.

This design defines the first additive story contract slice for that orchestration.

The v1 goal is simple:

- keep the existing story tools as the public entrypoints
- preserve concise story-first answers
- add structured GitOps, documentation, and support sections
- combine graph/context evidence with targeted Postgres content evidence

The user should be able to ask PCG for a story, a service explainer, an onboarding guide, or a support runbook without learning a separate tool.

## Product principle

Documentation generation is an orchestration problem.

- Story and context surfaces are the planner.
  They decide what is being explained, what evidence is still missing, and which drilldowns matter.
- Postgres-backed content retrieval is the evidence fetcher.
  It supplies exact file and snippet evidence once the story layer knows what it needs.
- Documentation output is the shaped result.
  It turns graph and content evidence into something a human can use quickly.

Without that orchestration, PCG can only summarize files or narrate graph relationships in isolation. With it, PCG can generate truthful service, deployment, and support documentation.

## V1 user-facing contract

V1 keeps these public tools as the primary story entrypoints:

- `get_repo_story`
- `get_workload_story`
- `get_service_story`
- `trace_deployment_chain`

The contract change is additive. Story payloads now support these optional sections:

- `gitops_overview`
- `documentation_overview`
- `support_overview`

Matching `story_sections` families are also additive:

- `gitops`
- `documentation`
- `support`

No existing story field is removed or renamed.

## Orchestration model

### Step 1: Start with graph/context

The story layer starts with canonical graph-backed context:

- repository ownership
- deployment paths
- workload instances
- infrastructure dependencies
- delivery controllers
- config repositories
- environments

This keeps the first answer concise and grounded in structured relationships.

### Step 2: Detect missing detail

The story layer decides whether the answer needs targeted content evidence.

Typical triggers:

- the user wants documentation or onboarding material
- the user asks for support or on-call guidance
- the graph identifies GitOps or deployment paths but not the exact files worth reading first
- the graph identifies config or deployment ownership and the answer benefits from exact repo-relative artifacts

### Step 3: Fetch targeted Postgres content

The story layer then fetches only the evidence needed for the documentation outcome:

- indexed file reads
- indexed content search
- cached entity source when available

The preferred path is always portable:

- `repo_id + relative_path`
- `entity_id`

V1 intentionally avoids bulk content expansion. It fetches targeted evidence only for high-signal artifacts such as README files, runbooks, docs pages, and GitOps config paths.

### Step 4: Shape the answer for the audience

The combined evidence is shaped into one or more of these documentation outcomes:

- code explanation docs
- service overview docs
- infra and deployment docs
- support and on-call docs

The top-level `story` stays concise. Deeper structured fields carry the longer-lived documentation scaffolding.

## Generic GitOps story model

The design target is generic ArgoCD plus Helm plus Kustomize estates, not one PCG-specific environment.

The desired narrative chain is:

1. ArgoCD owner
2. environment overlay
3. chart or release identity
4. ordered values layers
5. rendered workload resources
6. supporting Kustomize or sidecar resources
7. runtime components and dependencies

V1 does not fully derive every ArgoCD ownership detail yet, but it establishes the response shape that can carry that generic chain cleanly.

## New structured sections

### `gitops_overview`

Purpose:

- expose deployment provenance in a structured, reusable way

Fields:

- `owner`
- `environment`
- `chart`
- `value_layers`
- `rendered_resources`
- `supporting_resources`
- `limitations`

### `documentation_overview`

Purpose:

- expose a documentation-oriented summary and the evidence sources behind it

Fields:

- `audiences`
- `service_summary`
- `code_summary`
- `deployment_summary`
- `key_artifacts`
- `recommended_drilldowns`
- `documentation_evidence`
- `limitations`

`documentation_evidence` distinguishes:

- graph/context evidence
- Postgres file content
- Postgres entity content
- content search evidence

### `support_overview`

Purpose:

- specialize the documentation story for support and on-call usage

Fields:

- `runtime_components`
- `entrypoints`
- `dependency_hotspots`
- `investigation_paths`
- `key_artifacts`
- `limitations`

## Audience expectations

### Code explanation docs

Need:

- repo ownership
- code size and boundaries
- high-signal source files
- recommended drilldowns into content and code-query tools

### Service overview docs

Need:

- service summary
- runtime and environment context
- deployment provenance
- entrypoints and dependencies

### Infra and deployment docs

Need:

- GitOps delivery chain
- values and overlay layers
- rendered and supporting resources
- environment-specific hints

### Support and on-call docs

Need:

- runtime components
- public or internal entrypoints
- likely failure domains
- first investigation paths
- exact artifacts worth opening first

## Truthfulness rules

The orchestration layer must stay explicit about what it knows and what it does not.

- Do not invent runbook guidance when the graph or content store does not support it.
- Do not silently treat missing content evidence as absence of docs.
- Do not silently treat sparse graph evidence as proof that a GitOps layer does not exist.
- Prefer explicit `limitations` over omission.

If a story is built from graph-only evidence, say so.
If documentation evidence came from Postgres file or search results, say so.

## V1 scope

Included:

- additive story contract changes
- reusable GitOps, documentation, and support shaping helpers
- targeted Postgres content evidence for story answers
- repo, workload, service, and deployment-chain support for the new fields
- public docs and prompt guidance

Deferred:

- a separate `get_documentation_story` or `get_gitops_story` tool
- exhaustive ArgoCD owner inference for every estate shape
- automatic multi-file synthesized runbook generation as a first-class export artifact
- broad persona-specific template engines

## Acceptance criteria

1. Story surfaces can expose `gitops_overview`, `documentation_overview`, and `support_overview` without breaking existing callers.
2. Documentation-oriented answers can combine graph/context evidence with targeted Postgres content evidence.
3. Support answers stay evidence-backed and expose useful first investigation paths.
4. Missing graph or content evidence produces explicit limitations instead of silent gaps.
5. The response shape remains small enough for MCP, HTTP, and prompt-driven use.
