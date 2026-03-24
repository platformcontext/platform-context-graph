# Templated Infrastructure Parsing Design

## Goal

Parse authored infrastructure files that contain Helm/Argo Go templates, Jinja-family template syntax, and Terraform/HCL interpolation without rendering them during indexing.

The system must preserve raw template source as the canonical artifact for debugging and search, while extracting structure only when it can do so safely.

## Ground Truth From The Inventory Spike

The repo inventory spike established that this is a real authored-code problem, not a small corner case:

- `iac-eks-addons`: `plain_yaml=316`, `go_template_yaml=4`
- `iac-eks-argocd`: `plain_yaml=94`, `go_template_yaml=99`, `terraform_hcl=8`, `terraform_hcl_templated=3`
- `iac-eks-crossplane`: `plain_yaml=106`, `terraform_hcl=30`, `terraform_hcl_templated=1`
- `iac-eks-observability`: `plain_yaml=111`, `go_template_yaml=3`
- `iac-eks-pcg`: `plain_yaml=23`, `go_template_yaml=13`, `helm_helper_tpl=1`
- `argocd-env-generator`: `plain_yaml=3`, `go_template_yaml=3`
- `ansible-automate`: `plain_yaml=483`, `jinja_yaml=593`, `unknown_templated=171`, ambiguous `3`
- `bg-dagster`: `plain_yaml=16`, `jinja_yaml=29`, `terraform_hcl=4`, `terraform_hcl_templated=9`
- `terraform-modules`: `plain_yaml=34`, `terraform_hcl=1947`, `terraform_hcl_templated=1043`, `unknown_templated=264`, ambiguous `8`

The spike also confirmed two important realities:

- generated/vendor trees such as `.terraform` and `.worktrees` must be excluded by default or they drown the authored surface
- ambiguity is concentrated in a small, real subset of files and should be surfaced, not silently guessed away

## Requirements

- Keep raw authored source as the canonical stored content.
- Do not render templates during v1 indexing.
- Fail closed when a file is ambiguous or cannot be normalized safely.
- Reduce warning spam from templated YAML/HCL that the dialect layer claims.
- Improve structural extraction for authored templated files without inventing false resources or edges.
- Keep Helm helper `.tpl` files as raw-source artifacts in v1; do not pretend they are ordinary YAML resources.

## Chosen V1 Contract

### 1. Raw is canonical

The content store keeps the authored template exactly as written.

Generated/rendered content is optional future work, not a requirement for v1. If a later phase stores derived output, it must be:

- deterministic
- offline
- context-complete enough to trust
- clearly labeled as derived, not canonical

### 2. Parsing is non-rendering

The parser pipeline will:

- detect the template dialect
- normalize the file into a parse-safe candidate where possible
- run the existing YAML or HCL extraction on that candidate
- keep raw source unchanged in storage

This is intentionally not the same as executing Helm, Argo, Jinja, Ansible, Terragrunt, or Terraform.

### 3. Fail closed on ambiguity

If a file mixes dialect markers in a way the detector cannot classify confidently, v1 will:

- preserve raw source
- record the file as ambiguous
- skip structural extraction for that file

The system should prefer missing structure over wrong structure.

## Scope And Dialects

### Go-template YAML

Applies to:

- Helm chart templates under `templates/*.yaml`
- Argo/ApplicationSet YAML using Go-template syntax
- templated values files that embed `{{ ... }}` control or insertion blocks

V1 behavior:

- detect Go-template spans
- normalize scalar and block insertions into YAML-safe placeholders
- strip standalone control lines when they are structural wrappers
- then pass the normalized document to the existing YAML extractor

### Jinja-family YAML

Applies to:

- `bg-dagster`
- Ansible playbooks/vars with Jinja syntax
- `.j2`, `.jinja`, `.jinja2`, and YAML files containing Jinja markers

V1 behavior:

- detect `{% ... %}`, `{# ... #}`, and `{{ ... }}`
- normalize expression-only scalars and standalone control blocks
- leave raw authored source unchanged in storage
- skip extraction when Jinja/Go markers mix ambiguously

### Terraform/HCL templating

Applies to:

- `${...}`
- `%{ ... }`
- `templatefile(...)`
- templated heredocs and strings inside `.tf`, `.hcl`, `.tfvars`, and `.tftpl`

V1 behavior:

- keep the existing HCL parser path
- add template-aware normalization only where interpolation would otherwise break extraction
- continue to extract Terraform resources, variables, outputs, modules, and data sources when the HCL structure is still recoverable

## Implementation Plan

### Slice 1: Shared templated-file detector

Create a reusable dialect detector in `src/platform_context_graph/tools/languages/` that:

- classifies authored files into Go-template YAML, Jinja YAML, Terraform/HCL templated, or ambiguous
- reuses the inventory spike heuristics as the starting point
- excludes generated/vendor paths by default when running corpus-oriented tooling

This detector becomes the entry point for later normalization work.

### Slice 2: Non-rendering YAML normalization

Add a shared normalization layer for templated YAML that:

- handles Helm/Argo Go-template YAML
- handles Jinja-family YAML
- produces a parse-safe YAML candidate without rendering
- records why a file was normalized or skipped

Normalization rules should be context-shaped:

- expression in scalar position -> stable scalar placeholder
- mapping insertion position -> `{}` placeholder
- sequence insertion position -> `[]` placeholder
- standalone control wrappers -> removed from the parse candidate, but recorded in metadata

### Slice 3: HCL template-awareness

Extend the current Terraform/HCL parsing path so interpolation-heavy files do not degrade extraction unnecessarily.

This is not a full HCL parser rewrite in v1.

### Slice 4: Parser integration and warning cleanup

Once the detector and normalizers exist:

- route claimed templated files through the dialect-aware path first
- suppress raw PyYAML-style warning floods for those files
- emit one concise warning per file when normalization fails or ambiguity forces a skip

## Public And Internal Interfaces

No HTTP or MCP interface changes are required in v1.

Internal additions:

- shared template dialect detection helper
- normalization result object containing:
  - dialect
  - normalized text
  - ambiguity flag
  - skip reason
  - renderability hint

The content store remains raw-source-first.

## Testing

### Unit tests

- Helm chart templates from `iac-eks-pcg`
- Argo templated YAML from `iac-eks-argocd`
- Jinja YAML from `bg-dagster`
- Ansible YAML from `ansible-automate`
- Terraform interpolation and template cases from `terraform-modules`
- ambiguous mixed-marker cases that must fail closed

### Integration tests

- `iac-eks-pcg` indexes without Helm template parse spam
- `bg-dagster` indexes without Jinja YAML parse spam
- templated Terraform files still produce structural Terraform entities
- files marked ambiguous skip extraction but remain available as raw source

### Acceptance checks

- raw authored templates remain retrievable exactly as stored
- templated authored files no longer flood logs with generic YAML parse errors when the dialect layer claims them
- ambiguous files are surfaced explicitly instead of guessed
- structural extraction improves on Helm/Argo/Jinja/Terraform authored files that are normalizable without rendering

## Non-Goals

- generic template rendering in v1
- executing Helm, Argo, Ansible, or Terraform to produce cluster-specific output
- storing rendered output by default
- extracting resources from Helm helper `.tpl` files in v1

## Defaults

- raw authored template content is mandatory
- derived/generated content is optional future work only
- ambiguity is a hard stop for structural extraction
- warning reduction must not come at the cost of silently inventing structure
