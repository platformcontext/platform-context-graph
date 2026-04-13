# Groovy Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/groovy.yaml`

## Parser Contract
- Language: `groovy`
- Family: `language`
- Parser: `DefaultEngine (groovy)`
- Entrypoint: `go/internal/parser/groovy_language.go`
- Fixture repo: `tests/fixtures/ecosystems/groovy_comprehensive/`
- Unit test suite: `go/internal/parser/groovy_language_test.go`
- Integration test suite: `tests/integration/mcp/test_repository_runtime_context.py`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Jenkins shared libraries | `jenkins-shared-libraries` | supported | `shared_libraries` | `shared_libraries` | `property:File.shared_libraries` | `go/internal/parser/groovy_language_test.go::TestDefaultEngineParsePathGroovyJenkinsfile` | `tests/integration/mcp/test_repository_runtime_context.py::test_trace_deployment_chain_tool_surfaces_runtime_context_and_limitations` | - |
| Jenkins pipeline entry calls | `jenkins-pipeline-calls` | supported | `pipeline_calls` | `pipeline_calls` | `property:File.pipeline_calls` | `go/internal/parser/groovy_language_test.go::TestDefaultEngineParsePathGroovyJenkinsfile` | `tests/integration/mcp/test_repository_runtime_context.py::test_trace_deployment_chain_tool_surfaces_runtime_context_and_limitations` | - |
| Jenkins deployment entry points | `jenkins-entry-points` | supported | `entry_points` | `entry_points` | `property:File.entry_points` | `go/internal/parser/groovy_language_test.go::TestDefaultEngineParsePathGroovyJenkinsfile` | `tests/integration/mcp/test_repository_runtime_context.py::test_trace_deployment_chain_tool_surfaces_runtime_context_and_limitations` | - |
| Jenkins deployment hints | `jenkins-deploy-hints` | supported | `jenkins_pipeline_metadata` | `use_configd, has_pre_deploy` | `property:File` | `go/internal/parser/groovy_language_test.go::TestDefaultEngineParsePathGroovyJenkinsfile` | `tests/integration/mcp/test_repository_runtime_context.py::test_trace_deployment_chain_tool_surfaces_runtime_context_and_limitations` | - |
| Jenkins shell command hints | `jenkins-shell-commands` | supported | `shell_commands` | `shell_commands` | `property:File.shell_commands` | `go/internal/parser/groovy_language_test.go::TestDefaultEngineParsePathGroovyJenkinsfileAnsibleHints` | `tests/integration/mcp/test_repository_runtime_context.py::test_trace_deployment_chain_tool_surfaces_runtime_context_and_limitations` | - |
| Jenkins Ansible playbook hints | `jenkins-ansible-hints` | supported | `ansible_playbook_hints` | `playbook, command` | `property:File.ansible_playbook_hints` | `go/internal/parser/groovy_language_test.go::TestDefaultEngineParsePathGroovyJenkinsfileAnsibleHints` | `tests/integration/mcp/test_repository_runtime_context.py::test_trace_deployment_chain_tool_surfaces_runtime_context_and_limitations` | - |

## Known Limitations
- Generic Groovy source is indexed conservatively; the current parser focuses on Jenkins pipeline metadata rather than broad class and method extraction
- Jenkins metadata is strongest for Jenkinsfile-style entrypoints and may not detect custom shared-library DSLs that hide deployment semantics behind opaque helper calls
- Jenkins controller hints are intentionally shallow; deeper controller-driven automation meaning is assembled later from Ansible, inventory, vars, and runtime-family enrichment
