# Developing PlatformContextGraph

This document is for anyone writing code in this repo. It covers how the parser system works, how to add new language or IaC support, how integration testing is structured, and the spec-driven contract model that keeps everything honest.

For general contribution rules (PR hygiene, file length limits, branch naming), see [CONTRIBUTING.md](CONTRIBUTING.md).

## Development Environment

```bash
uv sync
uv run pcg --help
```

Pre-PR checks:

```bash
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
uv run black --check src tests
./tests/run_tests.sh fast
```

## Parser Architecture

PCG has two families of parsers, both registered through a single parser registry in `src/platform_context_graph/tools/graph_builder_parsers.py`.

### Language Parsers (tree-sitter)

These parse source code — Python, Go, TypeScript, Rust, Java, etc. They use tree-sitter grammars to extract functions, classes, imports, calls, and variables from an AST.

Each language gets:

- A parser class in `src/platform_context_graph/tools/languages/<lang>.py` (e.g., `PythonTreeSitterParser`)
- A support module in `languages/<lang>_support.py` containing the tree-sitter query definitions (`<LANG>_QUERIES`)
- An optional `pre_scan_<lang>()` function for fast symbol mapping before full parsing

The parser registry maps file extensions to parsers:

```python
_TREE_SITTER_PARSER_EXTENSIONS = (
    (".py", "python"),
    (".go", "go"),
    (".ts", "typescript"),
    # ...
)

_LANGUAGE_SPECIFIC_PARSERS = {
    "python": (".languages.python", "PythonTreeSitterParser"),
    "go": (".languages.go", "GoTreeSitterParser"),
    # ...
}
```

When a file is parsed, the registry resolves its extension to a `TreeSitterParser` wrapper, which delegates to the language-specific parser class.

### IaC Parsers

These parse infrastructure files — Terraform, Kubernetes manifests, Helm charts, ArgoCD, Crossplane, CloudFormation, Kustomize. They don't use tree-sitter. Instead:

- **Terraform/HCL**: `HCLTerraformParser` uses regex-based block extraction with brace matching
- **Everything YAML-based**: `InfraYAMLParser` acts as a dispatcher, routing YAML documents to the correct semantic parser based on content detection (apiVersion, kind, filename patterns)

The YAML dispatch chain:

```
InfraYAMLParser.parse()
  ├─ is_helm_chart(filename)        → parse_helm_chart()
  ├─ is_helm_values(filename)       → parse_helm_values()
  └─ For each YAML document:
      ├─ is_cloudformation_template()   → parse_cloudformation_template()
      ├─ is_kustomization()             → parse_kustomization()
      └─ By apiVersion + kind:
          ├─ is_argocd_application()    → parse_argocd_application()
          ├─ is_argocd_applicationset() → parse_argocd_applicationset()
          ├─ is_crossplane_xrd()        → parse_crossplane_xrd()
          ├─ is_crossplane_composition()→ parse_crossplane_composition()
          ├─ is_crossplane_claim()      → parse_crossplane_claim()
          └─ has apiVersion?            → parse_k8s_resource()
```

IaC parsers are registered conditionally based on config:

```python
if INDEX_YAML == "true":
    parsers[".yaml"] = InfraYAMLParser("yaml")
    parsers[".yml"]  = InfraYAMLParser("yaml")

if INDEX_HCL == "true":
    parsers[".tf"]  = HCLTerraformParser("hcl")
    parsers[".hcl"] = HCLTerraformParser("hcl")
```

## The Parser Contract

Every parser — language or IaC — returns a dict with a standardized shape. Language parsers return:

```python
{
    "path": str,
    "lang": str,
    "is_dependency": bool,
    "functions": [{"name", "line_number", "end_line", "args", "lang", ...}],
    "classes": [{"name", "line_number", "end_line", "bases", "lang", ...}],
    "imports": [{"name", "source", "alias", "line_number", "lang"}],
    "function_calls": [{"name", "line_number", ...}],
    "variables": [{"name", "line_number", ...}],
    # Language-specific: "interfaces", "traits", "structs", "enums", etc.
}
```

IaC parsers return the same top-level shape but populate different keys:

```python
{
    "path": str,
    "lang": str,
    "terraform_resources": [...],      # TerraformResource nodes
    "k8s_resources": [...],            # K8sResource nodes
    "argocd_applications": [...],      # ArgoCDApplication nodes
    "helm_charts": [...],              # HelmChart nodes
    "crossplane_xrds": [...],         # CrossplaneXRD nodes
    # etc.
}
```

Each key maps to a Neo4j node label via `ITEM_MAPPINGS_KEYS` in `graph_builder_persistence_unwind.py`. During persistence, all items are MERGEd into the graph using UNWIND queries.

## Spec-Driven Capability Model

We don't trust prose docs to stay in sync with parser behavior. Instead, each parser has a machine-readable capability spec:

```
src/platform_context_graph/tools/parser_capabilities/specs/<language>.yaml
```

Each spec records what the parser claims to extract, what the graph actually surfaces, which tests prove it, and what's intentionally partial or unsupported. The status semantics are strict:

- **supported**: extracted, surfaced end-to-end, covered by unit and integration tests
- **partial**: only the documented subset is promised
- **unsupported**: intentionally not claimed, but still documented

The per-language docs (`docs/docs/languages/*.md`) and the feature matrix (`docs/docs/languages/feature-matrix.md`) are generated from these specs. Don't hand-edit them.

```bash
# Generate docs from specs
PYTHONPATH=src uv run python scripts/generate_language_capability_docs.py

# Check for drift between specs and docs
PYTHONPATH=src uv run python scripts/generate_language_capability_docs.py --check
```

The full contract model is documented in [docs/docs/contributing-language-support.md](docs/docs/contributing-language-support.md).

## Adding a New Language Parser

### 1. Write the test fixture first

Create `tests/fixtures/ecosystems/<lang>_comprehensive/` with source files that exercise the features you plan to support — functions, classes, imports, calls, inheritance, language-specific constructs.

### 2. Write unit tests

Add `tests/unit/parsers/test_<lang>_parser.py`. Each test should instantiate the parser directly and verify extraction from a small code snippet:

```python
@pytest.fixture(scope="class")
def parser():
    manager = get_tree_sitter_manager()
    wrapper = MagicMock()
    wrapper.language_name = "<lang>"
    wrapper.language = manager.get_language_safe("<lang>")
    wrapper.parser = manager.create_parser("<lang>")
    return <Lang>TreeSitterParser(wrapper)

def test_parse_functions(parser, temp_test_dir):
    code = "..."
    f = temp_test_dir / "test.<ext>"
    f.write_text(code)
    result = parser.parse(str(f))
    assert len(result["functions"]) == 1
```

### 3. Implement the parser

Create `src/platform_context_graph/tools/languages/<lang>.py` and `<lang>_support.py`:

- Define `<LANG>_QUERIES` with tree-sitter queries for functions, classes, imports, calls, variables
- Implement `<Lang>TreeSitterParser` with `__init__` and `parse` methods
- Implement `pre_scan_<lang>()` for import resolution

Use `tree-sitter parse` on sample code to inspect the AST and find the right node types.

### 4. Register the parser

In `graph_builder_parsers.py`, add entries to:

- `_TREE_SITTER_PARSER_EXTENSIONS` — map file extensions to the language name
- `_LANGUAGE_SPECIFIC_PARSERS` — map the language name to the module and class

### 5. Add integration tests

Add a test class to `tests/integration/test_language_graph.py` that indexes the fixture ecosystem and verifies nodes/relationships exist in the graph.

### 6. Write the capability spec

Create `src/platform_context_graph/tools/parser_capabilities/specs/<lang>.yaml` documenting each capability with its status, test references, and rationale.

### 7. Regenerate docs

```bash
PYTHONPATH=src uv run python scripts/generate_language_capability_docs.py
```

## Adding a New IaC Parser

IaC parsers follow the same contract model but use different detection and extraction patterns.

### For a new YAML-based format:

1. Create `src/platform_context_graph/tools/languages/<format>.py` with:
   - A detection function: `is_<format>(doc: dict) -> bool`
   - A parse function: `parse_<format>(doc: dict, path: str, ...) -> dict`

2. Register the detection/parse pair in `yaml_infra.py`'s `_DOCUMENT_PARSERS` tuple.

3. Add the new node label to `graph_builder_schema.py` (constraints and indexes).

4. Add the persistence mapping to `ITEM_MAPPINGS_KEYS` in `graph_builder_persistence_unwind.py`.

5. If the format has cross-repo relationships, add linking logic to `cross_repo_linker.py`.

### For a non-YAML format:

Create a standalone parser class (like `HCLTerraformParser`) and register it in `build_parser_registry()`.

## Integration Testing with Docker Compose

Unit tests run without external services. Integration tests need Neo4j. The docker compose stack gives you a full local environment.

### Starting the stack

```bash
docker compose up --build
```

This starts:

- **Neo4j** (ports 7474/7687) — the graph database
- **Postgres** (port 5432) — content store for portable retrieval
- **bootstrap-index** — indexes fixture repos from `tests/fixtures/ecosystems/`
- **platform-context-graph** — the API service on port 8080
- **repo-sync** — continuous re-index loop

If ports conflict:

```bash
NEO4J_HTTP_PORT=17474 NEO4J_BOLT_PORT=17687 PCG_HTTP_PORT=18080 docker compose up --build
```

### Running integration tests against the stack

With the stack running:

```bash
NEO4J_URI=bolt://localhost:7687 \
NEO4J_USERNAME=neo4j \
NEO4J_PASSWORD=testpassword \
DATABASE_TYPE=neo4j \
uv run python -m pytest tests/integration/ -v
```

The integration test fixtures in `tests/integration/conftest.py` automatically index all ecosystem fixture repos into Neo4j when the `indexed_ecosystems` fixture is used.

### What the ecosystem fixtures cover

The `tests/fixtures/ecosystems/` directory contains 34 fixture repos — one per language and IaC format, plus cross-cutting scenarios:

- **Language repos**: `python_comprehensive/`, `go_comprehensive/`, `typescript_comprehensive/`, etc.
- **IaC repos**: `terraform_comprehensive/`, `kubernetes_comprehensive/`, `argocd_comprehensive/`, `crossplane_comprehensive/`, etc.
- **Cross-cutting**: `python_terraform/`, `python_crossplane/`, `shared_infra_platform/`

These are real (small) codebases with realistic structure. Integration tests index them and query the graph to verify end-to-end behavior.

## Test Layers

| Layer | What it tests | Needs Neo4j | Command |
|-------|---------------|-------------|---------|
| Unit | Parser extraction, query logic, domain models | No | `./tests/run_tests.sh unit` |
| Integration | Graph persistence, API contracts, MCP routing, CLI behavior | Yes | `./tests/run_tests.sh integration` |
| Deployment | Helm templates, Kustomize manifests, Compose assets | No | `pytest tests/integration/deployment/` |
| E2E | Full user journeys via CLI subprocess | Yes + full stack | `./tests/run_tests.sh e2e` |

Fast local pass (unit + integration):

```bash
./tests/run_tests.sh fast
```

### Test locations

- `tests/unit/parsers/` — parser extraction tests (31 files)
- `tests/unit/query/` — query logic tests
- `tests/integration/test_language_graph.py` — language graph verification
- `tests/integration/test_iac_graph.py` — IaC graph verification
- `tests/integration/test_full_flow.py` — cross-repo linking
- `tests/integration/api/` — HTTP API contract tests
- `tests/integration/mcp/` — MCP tool routing tests
- `tests/integration/cli/` — CLI command tests
- `tests/e2e/` — end-to-end user journeys

## Cross-Repo Linking

After indexing, `CrossRepoLinker` creates relationships between IaC nodes across repos:

| Relationship | From | To | How |
|---|---|---|---|
| `SOURCES_FROM` | ArgoCDApplication | Repository | URL match on source_repo |
| `SATISFIED_BY` | CrossplaneClaim | CrossplaneXRD | claim.kind = xrd.claim_kind |
| `IMPLEMENTED_BY` | CrossplaneXRD | CrossplaneComposition | composite_kind match |
| `USES_MODULE` | TerraformModule | Repository | module source contains repo name |
| `DEPLOYS` | ArgoCDApplication | K8sResource | namespace + source repo match |
| `CONFIGURES` | HelmValues | HelmChart | path colocation |
| `SELECTS` | K8sResource (Service) | K8sResource (Deployment) | name + namespace match |
| `USES_IAM` | K8sResource (ServiceAccount) | TerraformResource | IRSA annotation |
| `ROUTES_TO` | K8sResource (HTTPRoute) | K8sResource (Service) | backend_refs |
| `PATCHES` | KustomizeOverlay | K8sResource | resource path match |
| `RUNS_IMAGE` | K8sResource | Repository | container image match |

This is what makes bidirectional tracing work — from a running workload back to the Terraform module that provisions its IAM role, or from code forward through ArgoCD to the Kubernetes resources it deploys.

## Graph Schema

Node types and their uniqueness constraints are defined in `src/platform_context_graph/tools/graph_builder_schema.py`.

**Code nodes**: `File`, `Function`, `Class`, `Module`, `Interface`, `Trait`, `Struct`, `Enum`, `Macro`, `Variable`

**IaC nodes**: `K8sResource`, `ArgoCDApplication`, `ArgoCDApplicationSet`, `CrossplaneXRD`, `CrossplaneComposition`, `CrossplaneClaim`, `KustomizeOverlay`, `HelmChart`, `HelmValues`, `TerraformResource`, `TerraformVariable`, `TerraformOutput`, `TerraformModule`, `TerraformDataSource`, `TerragruntConfig`, `CloudFormationResource`, `CloudFormationParameter`, `CloudFormationOutput`

**Materialized**: `Repository`, `Workload`, `Environment`
