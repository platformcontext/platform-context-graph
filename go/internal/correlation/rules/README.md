# Correlation Rules

`correlation/rules` defines the declarative rule-pack schema and the
first-party rule packs PCG ships for container, IaC, and CI/CD correlation
families.

## Purpose

Express each correlation family as a `RulePack` of bounded `Rule` entries
plus structural `EvidenceRequirement` selectors. The engine consumes these
packs verbatim; the rules package owns no evaluation logic, only schema
definition and pack constructors.

## Ownership boundary

- Owns: `RuleKind`, `EvidenceField`, `EvidenceSelector`,
  `EvidenceRequirement`, `Rule`, `RulePack`, and the per-family pack
  constructors.
- Does not own: candidate evaluation (`engine`), admission gating
  (`admission`), or explain rendering (`explain`).

## Exported surface

Schema:

- `RuleKind` constants: `RuleKindExtractKey`, `RuleKindMatch`, `RuleKindAdmit`,
  `RuleKindDerive`, `RuleKindExplain`.
- `EvidenceField` constants: `EvidenceFieldSourceSystem`,
  `EvidenceFieldEvidenceType`, `EvidenceFieldScopeID`, `EvidenceFieldKey`,
  `EvidenceFieldValue`.
- `EvidenceSelector`, `EvidenceRequirement`, `Rule`, `RulePack`, each with a
  `Validate` method.

First-party rule pack constructors (one per file):

- `AnsibleRulePack` (`ansible_rules.go`)
- `ArgoCDRulePack` (`argocd_rules.go`)
- `CloudFormationRulePack` (`cloudformation_rules.go`)
- `DockerComposeRulePack` (`docker_compose_rules.go`)
- `DockerfileRulePack` (`dockerfile_rules.go`)
- `GitHubActionsRulePack` (`github_actions_rules.go`)
- `HelmRulePack` (`helm_rules.go`)
- `JenkinsRulePack` (`jenkins_rules.go`)
- `KustomizeRulePack` (`kustomize_rules.go`)
- `TerraformConfigRulePack` (`terraform_config_rules.go`)
- `TerragruntRulePack` (`terragrunt_rules.go`)

Aggregated entry points:

- `ContainerRulePacks()` returns the initial container correlation slice
  (Dockerfile, Docker Compose, GitHub Actions, Jenkins, Helm, ArgoCD,
  Kustomize, Terraform config, CloudFormation).
- `FirstPartyRulePacks()` returns every shipped pack; it adds Terragrunt and
  Ansible to the container slice.

## Dependencies

Standard library only.

## Telemetry

None. Schema and constructors only.

## Gotchas / invariants

- `RulePack.Validate` requires `MinAdmissionConfidence` in `[0, 1]`, at least
  one `Rule`, non-blank rule names, valid `RuleKind`, non-negative `Priority`,
  and non-negative `MaxMatches`.
- `EvidenceRequirement.MinCount` must be positive and `MatchAll` must contain
  at least one selector. `Validate` rejects whitespace-only selector values.
- `ContainerRulePacks` and `FirstPartyRulePacks` differ: do not assume
  callers share the same set. `ContainerRulePacks` excludes Terragrunt and
  Ansible.

## Related docs

- `go/internal/correlation/engine/README.md`
- `go/internal/correlation/admission/README.md`
- `go/internal/correlation/README.md`
