# Crossplane Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/tools/parser_capabilities/specs/crossplane.yaml`

## Parser Contract
- Language: `crossplane`
- Family: `iac`
- Parser: `InfraYAMLParser`
- Entrypoint: `src/platform_context_graph/tools/languages/yaml_infra.py`
- Fixture repo: `tests/fixtures/ecosystems/crossplane_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_yaml_infra_parser.py`
- Integration test suite: `tests/integration/test_iac_graph.py::TestCrossplaneGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Composite Resource Definitions (XRDs) | `composite-resource-definitions-xrds` | supported | `crossplane_xrds` | `name, line_number` | `node:CrossplaneXRD` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_crossplane_xrd` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_xrd_indexed` | - |
| XRD group, kind, version | `xrd-group-kind-version` | supported | `properties` | `name, line_number, kind, group, version` | `property:XRD.properties` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_crossplane_xrd` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_xrd_indexed` | - |
| Compositions | `compositions` | supported | `crossplane_compositions` | `name, line_number` | `node:CrossplaneComposition` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_crossplane_composition` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_composition_indexed` | - |
| Composition composite type ref | `composition-composite-type-ref` | supported | `crossplane_compositions` | `name, line_number, composite_type_ref` | `property:Composition.composite_type_ref` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_crossplane_composition` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_composition_indexed` | - |
| Composition resources list | `composition-resources-list` | supported | `k8s_resources` | `name, line_number, resources` | `property:Composition.resources` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_no_k8s_standalone_resources_without_api_version` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_composition_indexed` | - |
| Claims | `claims` | supported | `crossplane_claims` | `name, line_number` | `node:CrossplaneClaim` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_crossplane_claim` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_claim_indexed` | - |
| Claim composite type ref | `claim-composite-type-ref` | supported | `crossplane_claims` | `name, line_number, composite_type_ref` | `property:Claim.composite_type_ref` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_crossplane_claim` | `tests/integration/test_iac_graph.py::TestCrossplaneGraph::test_crossplane_claim_indexed` | - |

## Known Limitations
- Composition patch transforms are not modeled as graph edges
- XRD validation schema details are not extracted
- Usage of Composition Functions (pipeline steps) is not captured as structured nodes
