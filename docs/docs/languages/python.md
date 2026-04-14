# Python Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `python`
- Family: `language`
- Parser: `DefaultEngine (python)`
- Entrypoint: `go/internal/parser/python_language.go`
- Fixture repo: `tests/fixtures/ecosystems/python_comprehensive/`
- Unit test suite: `go/internal/parser/engine_python_semantics_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestPythonGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | `tests/integration/test_language_graph.py::TestPythonGraph::test_entity_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | `tests/integration/test_language_graph.py::TestPythonGraph::test_entity_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | `tests/integration/test_language_graph.py::TestPythonGraph::test_import_edges_created` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | `tests/integration/test_language_graph.py::TestPythonGraph::test_function_call_edges_created` | - |
| Variables | `variables` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | `tests/integration/test_language_graph.py::TestPythonGraph::test_variable_nodes_created` | - |
| Decorators | `decorators` | unsupported | `functions` | `name, line_number, decorators` | `none:not_persisted` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonDecoratedFunctionsEmitDecoratorMetadata` | `tests/integration/test_language_graph.py::TestPythonGraph::test_decorator_metadata_not_persisted` | The Go parser now emits decorator metadata, but the graph surface does not yet persist decorators as first-class queryable properties. |
| Async functions | `async-functions` | unsupported | `functions` | `name, line_number, async` | `none:not_persisted` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonAsyncFunctionsEmitAsyncFlag` | `tests/integration/test_language_graph.py::TestPythonGraph::test_async_flag_not_persisted` | The Go parser now emits the async flag, but the graph surface does not yet retain it as a queryable property. |
| Inheritance | `inheritance` | supported | `classes` | `name, line_number, bases` | `relationship:INHERITS` | `go/internal/parser/engine_test.go::TestDefaultEngineParsePathPython` | `tests/integration/test_language_graph.py::TestPythonGraph::test_inheritance_edges` | - |
| Type annotations | `type-annotations` | unsupported | `type_annotations` | `name, line_number, type` | `none:not_persisted` | `go/internal/parser/engine_python_semantics_test.go::TestDefaultEngineParsePathPythonEmitsTypeAnnotationsBucket` | `tests/integration/test_language_graph.py::TestPythonGraph::test_type_annotation_nodes_not_created` | The Go parser emits a dedicated `type_annotations` bucket, but the graph surface does not yet materialize TypeAnnotation nodes end to end. |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `supported`
- Framework packs: `fastapi-base`, `flask-base`
- Query surfacing: `supported`
- Real-repo validation: `supported`
- End-to-end indexing: `supported`
- Local repo validation evidence:
  - `recos-ranker-service (clean end-to-end validation with FastAPI framework evidence)`
  - `lambda-python-s3-proxy (clean end-to-end validation with Flask framework evidence)`
  - `lambda-python-lb-s3-files (discovery-aware parser validation with Flask route evidence)`
- Notes:
  - recos-ranker-service completed a clean local end-to-end indexing run (run 1cfe41a63cb2bd4a)
  - lambda-python-s3-proxy completed a clean local end-to-end indexing run (run 6a792e3bb05f5c69)
  - repo context, repo summary, and repo story all surfaced FastAPI or Flask framework evidence through the default FalkorDB backend


## Known Limitations
- Lambda functions detected as unnamed functions
- Comprehension-internal functions not always tracked
- Metaclass relationships not captured
