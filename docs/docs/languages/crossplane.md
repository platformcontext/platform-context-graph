# Crossplane Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/crossplane.yaml`

## Parser Contract
- Language: `crossplane`
- Family: `iac`
- Parser: `DefaultEngine (yaml)`
- Entrypoint: `go/internal/parser/yaml_language.go`
- Fixture repo: `tests/fixtures/ecosystems/crossplane_comprehensive/`
- Unit test suite: `go/internal/parser/engine_yaml_semantics_test.go`
- Integration test suite: `tests/integration/test_iac_graph.py::TestCrossplaneGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Composite Resource Definitions (XRDs) | `composite-resource-definitions-xrds` | supported | `crossplane_xrds` | `name, line_number` | `node:CrossplaneXRD` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCrossplaneResources` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_xrd_indexed` | - |
| XRD group, kind, version | `xrd-group-kind-version` | supported | `properties` | `name, line_number, kind, group, claim_kind` | `property:XRD.properties` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCrossplaneResources` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_xrd_indexed` | - |
| Compositions | `compositions` | supported | `crossplane_compositions` | `name, line_number` | `node:CrossplaneComposition` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCrossplaneResources` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_composition_indexed` | - |
| Composition composite type ref | `composition-composite-type-ref` | supported | `crossplane_compositions` | `name, line_number, composite_api_version, composite_kind` | `property:Composition.composite_ref` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCrossplaneResources` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_composition_indexed` | - |
| Composition resources list | `composition-resources-list` | supported | `crossplane_compositions` | `name, line_number, resource_count, resource_names` | `property:Composition.resources` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCrossplaneResources` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_composition_indexed` | - |
| Claims | `claims` | supported | `crossplane_claims` | `name, line_number` | `node:CrossplaneClaim` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCrossplaneResources` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_claim_indexed` | - |
| Claim API version | `claim-api-version` | supported | `crossplane_claims` | `name, line_number, api_version` | `property:Claim.api_version` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCrossplaneResources` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_claim_indexed` | - |

## Known Limitations
- Composition patch transforms are not modeled as graph edges
- XRD validation schema details are not extracted
- Usage of Composition Functions (pipeline steps) is not captured as structured nodes
