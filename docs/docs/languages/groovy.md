# Groovy Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/tools/parser_capabilities/specs/groovy.yaml`

## Parser Contract
- Language: `groovy`
- Family: `language`
- Parser: `GroovyTreeSitterParser`
- Entrypoint: `src/platform_context_graph/tools/languages/groovy.py`
- Fixture repo: `tests/fixtures/ecosystems/groovy_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_groovy_parser.py`
- Integration test suite: `tests/integration/mcp/test_repository_runtime_context.py`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Jenkins shared libraries | `jenkins-shared-libraries` | supported | `shared_libraries` | `shared_libraries` | `property:File.shared_libraries` | `tests/unit/parsers/test_groovy_parser.py::test_parse_jenkinsfile_extracts_pipeline_metadata` | `tests/integration/mcp/test_repository_runtime_context.py::test_trace_deployment_chain_tool_surfaces_runtime_context_and_limitations` | - |
| Jenkins pipeline entry calls | `jenkins-pipeline-calls` | supported | `pipeline_calls` | `pipeline_calls` | `property:File.pipeline_calls` | `tests/unit/parsers/test_groovy_parser.py::test_parse_jenkinsfile_extracts_pipeline_metadata` | `tests/integration/mcp/test_repository_runtime_context.py::test_trace_deployment_chain_tool_surfaces_runtime_context_and_limitations` | - |
| Jenkins deployment entry points | `jenkins-entry-points` | supported | `entry_points` | `entry_points` | `property:File.entry_points` | `tests/unit/parsers/test_groovy_parser.py::test_parse_jenkinsfile_extracts_pipeline_metadata` | `tests/integration/mcp/test_repository_runtime_context.py::test_trace_deployment_chain_tool_surfaces_runtime_context_and_limitations` | - |
| Jenkins deployment hints | `jenkins-deploy-hints` | supported | `jenkins_pipeline_metadata` | `use_configd, has_pre_deploy` | `property:File` | `tests/unit/parsers/test_groovy_parser.py::test_parse_jenkinsfile_extracts_pipeline_metadata` | `tests/integration/mcp/test_repository_runtime_context.py::test_trace_deployment_chain_tool_surfaces_runtime_context_and_limitations` | - |

## Known Limitations
- Generic Groovy source is indexed conservatively; the current parser focuses on Jenkins pipeline metadata rather than broad class and method extraction
- Jenkins metadata is strongest for Jenkinsfile-style entrypoints and may not detect custom shared-library DSLs that hide deployment semantics behind opaque helper calls
