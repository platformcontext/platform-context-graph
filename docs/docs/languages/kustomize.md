# Kustomize Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `kustomize`
- Family: `iac`
- Parser: `DefaultEngine (yaml)`
- Entrypoint: `go/internal/parser/yaml_language.go`
- Fixture repo: `tests/fixtures/ecosystems/kustomize_comprehensive/`
- Unit test suite: `go/internal/parser/engine_yaml_semantics_test.go`
- Integration validation: compose-backed fixture verification (see [Local Testing Runbook](../reference/local-testing.md))

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Kustomization overlays (`kustomization.yaml`) | `kustomization-overlays-kustomization-yaml` | supported | `kustomize_overlays` | `name, line_number` | `node:KustomizeOverlay` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | Compose-backed fixture verification | - |
| Namespace | `namespace` | supported | `variables` | `name, line_number, namespace` | `property:Overlay.property` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | Compose-backed fixture verification | - |
| Resources list | `resources-list` | supported | `kustomize_overlays` | `name, line_number, resources` | `property:Overlay.resources` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | Compose-backed fixture verification | - |
| Patches list | `patches-list` | supported | `kustomize_overlays` | `name, line_number, patches` | `property:Overlay.patches` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | Compose-backed fixture verification | - |
| Base references | `base-references` | partial | `kustomize_overlays` | `name, line_number, resources` | `none:not_persisted` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | Compose-backed fixture verification | Base references remain part of the normalized `resources` list instead of a separate `bases` field in the native YAML payload. |

## Known Limitations
- Strategic merge patches are not parsed for the target resource they modify
- `components` and `configurations` sections are not extracted
- Inline patch bodies within `kustomization.yaml` are not traversed for field-level details
