# Relationship Mapping

PlatformContextGraph resolves repository-to-repository relationships in a dynamic, evidence-backed flow. The important part is not just what edges exist, but when each stage runs, which stage owns truth, and which results are only derived summaries for answering questions.

If you want public, example-driven diagrams of the relationship shapes this produces, see the [Relationship Graph Examples guide](../guides/relationship-graphs.md).

The rule of thumb is:

- index first
- link repos across checkout boundaries
- extract evidence from graph state and raw files
- resolve typed relationships with precedence rules
- derive summaries for repository context
- shape the final MCP/API answer from those summaries
- explain truthfulness and completeness explicitly when evidence is partial

## Ownership By Stage

One of the easiest ways to introduce bugs in dynamic mappings is to let one stage do the job of another. The table below is the guardrail.

| Stage | Owns | Allowed to emit | Must not do |
| :--- | :--- | :--- | :--- |
| Index | parsed files, graph entities, raw properties | graph state | infer cross-repo truth from partial data |
| Cross-repo linking | repo identity and reference normalization | candidate repo links | invent semantic relationship types |
| Evidence extraction | explainable facts from graph or files | evidence facts with `evidence_kind`, rationale, confidence | collapse meaning to `DEPENDS_ON` for convenience |
| Typed resolution | canonical meaning and precedence | typed canonical edges and compatibility derivations | shape user-facing prose |
| Repo-context enrichment | nearby supporting context | deployment artifacts, workflow summaries, consumer summaries | override canonical truth |
| MCP/API answer shaping | concise explanation | `story`, `deployment_overview`, notes | invent new edges or hide completeness gaps |

If a change feels ambiguous, start by asking which stage actually owns the decision. That usually reveals the right place to implement it.

## End-To-End Flow

```mermaid
flowchart TD
    A[Index committed repos] --> B[Cross-repo linking]
    B --> C[Evidence extraction]
    C --> D[Typed resolution]
    D --> E[Canonical resolved relationships]
    E --> F[Neo4j projection]
    E --> G[Derived summaries]
    G --> H[Repo context enrichment]
    F --> H
    H --> I[MCP / API answer shaping]
    I --> J[Truthfulness and completeness notes]

    classDef canonical fill:#e8f3ff,stroke:#2563eb,color:#0f172a;
    classDef derived fill:#ecfdf3,stroke:#059669,color:#052e16;
    class D,E,F canonical;
    class G,H,I,J derived;
```

## Traversal Rules

The repo-to-file traversal rule is now explicit:

- use `REPO_CONTAINS` for flat `Repository -> File` lookups
- use `CONTAINS*` only when you genuinely need directory ancestry, file-descendant entities, or arbitrary descendant traversal

That distinction matters because a lot of dynamic mapping work starts from repo-local files:

- Terraform and Terragrunt evidence often starts as `Repository -> File -> TerraformModule`
- GitOps and workflow evidence often starts as `Repository -> File -> K8sResource` or `Repository -> File -> workflow/config entity`
- MCP and query hot paths often need file counts, entrypoint scans, or content discovery without walking the directory tree

The safe pattern is:

```text
Repository -[:REPO_CONTAINS]-> File -[:CONTAINS*]-> entity
```

The unsafe pattern for flat lookups is:

```text
Repository -[:CONTAINS*]-> File
```

Keep `CONTAINS*` when the query is actually about the tree, not just about locating files inside a repo.

## Story-First Answer Contract

MCP and HTTP responses now intentionally expose a top-level `story` field on `get_repo_summary` and `trace_deployment_chain`.

Use it this way:

1. read `story` first for the concise answer
2. read `deployment_overview` next for grouped supporting context
3. read the detailed fields only when you need exact evidence rows, file paths, or artifact lists

That keeps answer shaping consistent:

- `story` is the short narrative
- `deployment_overview` is the grouped summary data
- raw fields are the evidence-heavy drill-down surface

Do not make the caller reconstruct the main narrative from `delivery_paths`, `consumer_repositories`, `hostnames`, and `deployment_artifacts` unless they explicitly need that level of detail.

### 1. Index

PCG starts with committed checkouts and the graph state created by indexing. Relationship mapping is intentionally post-index. We do not try to infer cross-repo truth from half-indexed repositories.

### 2. Cross-repo linking

The mapping code builds stable checkout identities, then matches repo references, paths, chart URLs, workflow refs, and related repo names against the local corpus. This is where a file-level token becomes a candidate cross-repo link.

### 3. Evidence extraction

Evidence comes from two places:

- graph-derived signals that already exist in the modeled graph
- raw file extractors that read checked-in infrastructure or workflow config

Each evidence fact stores the relationship type, confidence, rationale, and details needed to explain the match later.

### 4. Typed resolution

The resolver deduplicates evidence, applies assertions and rejections, and chooses the most truthful relationship type available. This is where precedence matters.

Canonical relationship types today are:

- `DEPENDS_ON`
- `DISCOVERS_CONFIG_IN`
- `DEPLOYS_FROM`
- `PROVISIONS_DEPENDENCY_FOR`

- `PROVISIONS_PLATFORM`
- `RUNS_ON`

Typed relationships are canonical. A compatibility `DEPENDS_ON` edge may be derived later so older query surfaces still work, but the typed edge is the actual statement of meaning.

### Resolution Precedence Order

When multiple signals compete, resolve in this order:

1. explicit assertions and rejections
2. typed relationships with direct tool-semantic evidence
3. typed relationships with weaker heuristic evidence
4. compatibility `DEPENDS_ON` derived from stronger typed edges
5. generic fallback only if no stronger truthful type exists

This is the main rule that keeps the graph from becoming a pile of vague `DEPENDS_ON` edges.

### 5. Derived summaries

After resolution, repository context enrichment builds derived summaries from the resolved relationships and related config repositories. These summaries are for answering questions, not for redefining canonical truth.

The current derived summaries include:

- `deployment_artifacts`
- `delivery_workflows`
- `delivery_paths`
- `consumer_repositories`
- `shared_config_paths`
- hostnames
- API surface hints

### 6. Repo context enrichment

The query layer uses the resolved relationships to look up related repositories and collect supporting context. This is where deployment artifacts are assembled from related repos and values-style files.

### 7. MCP / API answer shaping

The query surfaces do not invent new canonical relationships. They choose how to present the already-resolved evidence, derived summaries, and limitations.

### 8. Truthfulness and completeness notes

If evidence is incomplete, ambiguous, or corpus-specific, the answer should say so. Do not upgrade a weak signal into a strong semantic edge just to make the output look cleaner.

## Canonical Versus Derived

Canonical relationships live in the relationship store and are projected into Neo4j for queries. Derived data lives on the read side and is built from canonical relationships plus nearby repo content.

That distinction matters:

- canonical relationships answer "what was actually observed and resolved"
- derived summaries answer "what related context should be shown to the user"

Do not flatten every mapping into `DEPENDS_ON`. The more specific typed edge is what keeps the graph truthful.

### Why Direction Matters

Write the edge in the direction of the behavior being explained.

- `iac-eks-argocd -[:DISCOVERS_CONFIG_IN]-> iac-eks-observability`
- `api-node-whisper -[:DEPLOYS_FROM]-> helm-charts`
- `terraform-stack-external-search -[:PROVISIONS_DEPENDENCY_FOR]-> api-node-external-search`

If the source is the control plane, keep the control-plane source on the left. If the source is the deployed workload or service, keep that workload on the left.

### Typed Precedence

When the same pair can be described by both a typed relationship and a generic `DEPENDS_ON`, the typed edge wins. The resolver suppresses the generic candidate for the same implied pair, then may derive a compatibility `DEPENDS_ON` edge from the typed result unless that generic edge was explicitly rejected.

That keeps the graph:

- more precise
- more queryable
- less likely to overwrite a stronger semantic with a weaker one

## Current Tool Families

The current mapping and enrichment flow understands these families:

| Family | What it reads | What it is used for |
| :--- | :--- | :--- |
| Terraform | `app_repo`, `app_name`, `api_configuration`, Cloud Map names, config paths, GitHub references, platform metadata | `PROVISIONS_DEPENDENCY_FOR` and platform/runtime context |
| Terragrunt | Terraform source blocks, dependency blocks, shared inputs, wrapper config | Same semantic family as Terraform, with the same emphasis on truthful direction |
| GitHub Actions | reusable workflow calls, checkout targets, deploy steps, command gating | Delivery-path summaries and future deploy-source mappings when the repo link is explicit |
| Jenkins / Groovy | Jenkinsfile metadata, stage and command hints, reusable pipeline metadata | Delivery-path summaries and automation context |
| ArgoCD | ApplicationSet discovery targets, deploy-source repo URLs, destination clusters | `DISCOVERS_CONFIG_IN`, `DEPLOYS_FROM`, and `RUNS_ON` |
| Helm | chart metadata, values files, chart dependency references | `DEPLOYS_FROM` |
| Kustomize | `resources`, Helm blocks, image references, overlays | `DEPLOYS_FROM` |
| Platform / runtime context | workload and platform modeling resolved through mixed entity ids | `PROVISIONS_PLATFORM` and `RUNS_ON` |

The important constraint is not the tool name itself. The important constraint is whether the tool gives you a truthful, explainable source of repository or platform meaning.

## Terraform-Managed Runtime Variants

Terraform-managed runtime summaries need to stay broader than ECS, even when ECS is the first concrete example in our corpus. The parser and summary layers should capture generic deployment-oriented module attributes first, then let the mapping and answer-shaping layers decide whether those attributes describe ECS, Fargate, Elastic Beanstalk, Kubernetes, or another provider/runtime combination.

Today the `TerraformModule` entity exposes portable attributes such as:

- `deployment_name`
- `repo_name`
- `create_deploy`
- `cluster_name`
- `zone_id`
- `deploy_entry_point`

Those attributes are intentionally not ECS-only. They are a generic contract for Terraform module blocks that describe deployable workloads or runtime variants.

Use that contract in this order:

1. parse the module attributes as-is from Terraform or Terragrunt-managed HCL
2. preserve them on the `TerraformModule` entity
3. resolve canonical platform relationships separately
4. derive repo-context summaries such as `service_variants` from the enriched module metadata
5. only then explain ECS-specific, Fargate-specific, or provider-specific meaning in the answer layer

This keeps the parser portable and makes it safe for contributors to add future runtime families without rewriting the semantic contract.

The runtime-specific decision point now lives in a shared Terraform runtime-family registry. That registry owns family-scoped signals such as:

- cluster resource types
- cluster module source patterns
- service module source patterns
- non-cluster support module patterns
- repo-name and slug hints used by GitOps control-plane repositories

ECS and EKS are the first registered families. Future families such as Fargate or Elastic Beanstalk should extend that registry instead of introducing ad hoc checks in multiple layers.

That registry is intentionally shared across more than one stage:

- Terraform evidence extraction uses it to decide which module sources imply `RUNS_ON`
- infrastructure platform inference uses it to decide which repos `PROVISIONS_PLATFORM`
- GitOps platform inference uses it to interpret repo names and slugs before falling back to generic Kubernetes controller hints

### ECS As The First Example, Not The Final Shape

ECS currently uses these attributes to explain variants like direct CodeDeploy-backed services and background jobs. The same pattern should be used for future Terraform-managed deployment targets:

- Fargate or ECS variants can reuse `cluster_name`, `repo_name`, and `create_deploy`
- Elastic Beanstalk style modules can still use `deployment_name` and `deploy_entry_point`
- non-AWS runtimes can map their platform identifiers into the same canonical relationship flow, then optionally surface provider-specific details in the read-side summary

If a future runtime needs new module attributes, add them as generic deployment metadata first, document them here, and only then teach the answer-shaping layer how to describe them.

## Generic Runtime Extension Pattern

The runtime extension pattern should work whether the target is ECS, Fargate, Elastic Beanstalk, Kubernetes, or another cloud/runtime combination.

The sequence is:

```mermaid
flowchart LR
    A[Parse generic module metadata] --> B[Runtime-family registry]
    A2[GitOps repo and slug hints] --> B
    B --> C[Resolve platform identity]
    C --> D[Emit typed canonical edges]
    D --> E[Derive repo summaries]
    E --> F[Shape story-first answer]

    A1[deployment_name\nrepo_name\ncreate_deploy\ncluster_name\nzone_id\ndeploy_entry_point]
    A -.-> A1
```

The rule is:

- parser layer captures portable deployment concepts
- resolver layer decides canonical relationship meaning
- answer layer explains provider-specific meaning

That means:

- ECS can use `cluster_name`, `repo_name`, and `create_deploy`
- Fargate can reuse the same fields if the module still models a deployable service variant
- Elastic Beanstalk can rely on `deployment_name` and `deploy_entry_point`
- another cloud can still map into `Platform.kind`, `Platform.provider`, `PROVISIONS_PLATFORM`, and `RUNS_ON`

Do not create an ECS-only parser contract just because ECS is the first rich example.

### What To Add For A New Runtime

When a contributor adds support for another Terraform-managed runtime family, the change order should be:

1. extend the shared runtime-family registry with the new family signals
2. add generic parser attributes only if the runtime needs new portable deployment metadata
3. keep provider-specific interpretation out of the parser
4. resolve canonical platform relationships from those attributes plus surrounding infra evidence
5. add read-side summaries only after the canonical relationship meaning is correct
6. update the `story` shaping only after the lower layers are stable

If the feature skips straight to answer shaping, it will drift.

## Deployment Artifacts

Deployment artifacts are the derived pieces of repository context that help answer "what deploys from here?" after the canonical mapping has been resolved.

They are assembled from related repositories and values-style config, not invented from a single repo in isolation.

Examples include:

- Helm chart references and chart sources
- image repositories and tags
- service ports and gateway hints
- Kustomize resources and patches
- shared config paths across multiple deployment sources
- consumer-only repositories that call or reference the service without deploying it
- workflow refs that help explain the delivery path

Use deployment artifacts to enrich answers and summaries. Do not treat them as a replacement for the underlying relationship edge.

### Shared Config And Consumer Summaries

Two derived summaries are especially easy to overuse:

- `shared_config_paths`
- `consumer_repositories`

They should help answer:

- which repos appear to share config families with this service
- which repos reference or call this service without deploying it

They should not be used to invent deployment or provisioning relationships by themselves.

### Story Ordering

The top-level repository `story` is intentionally assembled in a fixed order so users get the highest-signal narrative first:

1. public entrypoints
2. API surface
3. deployment path
4. ingress or service-port cues
5. shared config families
6. consumer-only repositories
7. completeness or limitation notes

That order matters. For example, shared config hints should not appear before the deployment path, and consumer-only repos should not crowd out ingress or platform context.

`deployment_story` itself has an internal preference order:

1. workflow- and delivery-path-derived deployment lines
2. reusable-workflow handoff plus canonical deploy/provision/runtime context when explicit command rows are missing
3. controller-driven automation lines built from Jenkins or other controllers plus Ansible-style automation evidence
4. controller/runtime fallback lines built from deployment controllers, runtime platforms, and service variants

The reusable-workflow tier matters for repos that hand off deployment to a centralized automation repository. In that case PCG may still emit truthful `delivery_paths` when all of these are already known:

- the repo references a reusable workflow or automation repository
- canonical repo relationships already show deployment sources such as `DEPLOYS_FROM`
- canonical repo relationships already show provisioning sources such as `PROVISIONS_DEPENDENCY_FOR`
- runtime platforms already show where the workload runs

The controller-driven automation tier is for estates where deployment meaning is carried more by controllers and automation entrypoints than by GitHub Actions delivery rows. Jenkins and Ansible are the first example, but the pattern should stay generic:

- controller evidence identifies who starts the automation
- automation evidence identifies what runs, where it targets, and which runtime family it implies
- the resulting path is surfaced as read-side context and story shaping, not as a new canonical relationship family

Only after those three tiers fail should PCG fall back to controller/runtime summaries such as Terraform, CodeDeploy, or service-variant evidence.

### Controller-Driven Automation Extension Pattern

Controller-driven automation should follow the same staged ownership model as the Terraform runtime-family work:

```mermaid
flowchart LR
    A[Controller evidence\nJenkinsfile or Groovy pipeline] --> B[Automation evidence\nplaybooks inventory vars role entrypoints]
    B --> C[Runtime automation family]
    C --> D[controller_driven_paths]
    D --> E[delivery_paths and deployment_overview]
    E --> F[story]
```

Rules:

- controller extraction should stay tool-semantic and portable
- automation extraction should focus on high-signal surfaces first
- runtime-family inference should stay centralized
- answer shaping should consume the normalized path, not raw repo-specific heuristics

Do not collapse controller-driven automation directly into canonical `DEPLOYS_FROM` or `PROVISIONS_DEPENDENCY_FOR` edges unless the underlying canonical evidence really exists.

## Safe Extension

When adding a new mapping family, follow this order:

1. Decide the semantic relationship first.
2. Choose the best evidence source.
3. Emit explainable evidence with stable metadata.
4. Preserve typed precedence in the resolver.
5. Decide whether the new family should also feed repo-context enrichment.
6. Add positive and negative tests.
7. Validate on a mixed corpus, not just a single synthetic repo pair.

## Dynamic Mapping Checklist

Before merging a new mapping family or runtime interpretation, verify all of these:

1. The parser change is still generic and open-source portable.
2. The new evidence rows are explainable with file paths or graph sources.
3. The resolver precedence is explicit and tested.
4. The direction of the canonical edge matches the actual actor and target.
5. Compatibility `DEPENDS_ON` is derived only after the typed meaning is correct.
6. Repo-context enrichment uses the canonical edge instead of bypassing it.
7. MCP/API `story` gets clearer, not noisier.
8. Partial coverage still produces a truthful note instead of a confident omission.

### Pick The Semantic First

Ask what the source is doing:

- discovering config
- deploying from artifacts
- provisioning runtime resources
- depending on runtime resources

Then choose the most specific truthful type. Fall back to `DEPENDS_ON` only when a more specific type would be misleading or unsupported.

### Keep Evidence Explainable

Every evidence fact should carry:

- a stable `evidence_kind`
- the chosen `relationship_type`
- a confidence score
- a plain-language rationale
- file path or graph source details
- the extractor or family name

If someone cannot inspect the evidence and understand why the edge exists, the mapping is too opaque.

### Preserve Portable Semantics

Keep canonical rules portable and open-source friendly.

- Avoid company-specific repository naming rules as canonical truth.
- Avoid hidden local knowledge that only works in one corpus.
- If a heuristic is useful but narrow, keep it explainable and treat it as a heuristic, not a universal law.

## Observability And Verification

Relationship mapping uses the shared observability contract.

### Logging

Logs must stay JSON on stdout.

- keep stable machine-readable `event_name` values
- keep custom dimensions under `extra_keys`
- keep trace and correlation fields intact
- do not add ad hoc top-level log keys

Current relationship events include:

- `relationships.discover_file_evidence.completed`
- `relationships.discover_gitops_evidence.completed`
- `relationships.discover_evidence.completed`
- `relationships.persist_generation.completed`
- `relationships.project.completed`
- `relationships.resolve.completed`
- `relationships.resolve.failed`

### OTEL

Use OTEL spans around the extractor family and the overall resolve/project phases.

Current span families include:

- `pcg.relationships.discover_evidence`
- `pcg.relationships.discover_evidence.file`
- `pcg.relationships.discover_evidence.terraform`
- `pcg.relationships.discover_evidence.helm`
- `pcg.relationships.discover_evidence.kustomize`
- `pcg.relationships.discover_evidence.gitops`
- `pcg.relationships.discover_evidence.argocd`
- `pcg.relationships.resolve_repository_dependencies`
- `pcg.relationships.project`

### Required Tests

Every new mapping family should come with:

- unit tests for the extractor
- unit tests for resolver precedence or coexistence
- a negative test that proves unrelated repos stay unrelated
- a mixed-corpus validation run when the family changes answer shape

For this slice, the important relationship tests are in:

- `tests/unit/relationships/test_file_evidence.py`
- `tests/unit/relationships/test_resolver.py`

## Example Multi-Chain

One useful pattern from the local corpus is:

```text
iac-eks-argocd
  DISCOVERS_CONFIG_IN -> iac-eks-observability
  DISCOVERS_CONFIG_IN -> helm-charts

api-node-bw-home
  DEPLOYS_FROM -> helm-charts

api-node-external-search
  DEPLOYS_FROM -> helm-charts

api-node-whisper
  DEPLOYS_FROM -> helm-charts
```

That is more truthful than flattening everything into a generic dependency chain. It preserves the control-plane meaning of the ArgoCD repo while keeping downstream deployment answers queryable.
