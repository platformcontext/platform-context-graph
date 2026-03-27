# Generic Jenkins and Ansible Automation Path Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach PlatformContextGraph to recognize and explain generic Jenkins-driven Ansible delivery paths, correlate them with runtime-family hints, and surface truthful controller-driven automation stories in repository summaries and deployment traces.

**Architecture:** Keep canonical relationships small and stable. Add controller-driven automation as a read-side enrichment layer built from Jenkins/Groovy, Ansible playbooks, inventory, vars, and targeted role entrypoints; normalize runtime hints through a shared family seam; then feed the resulting paths into `delivery_paths`, `deployment_story`, `topology_story`, and MCP `story` output without hard-coding MWS, AWS, or one repository naming scheme.

**Tech Stack:** Python, pytest, tree-sitter Groovy, YAML parsing, MCP handlers, MkDocs

---

## File Structure

### Existing files to modify

- `src/platform_context_graph/tools/languages/groovy_support.py`
  - extend Jenkins metadata extraction with controller and shell-command hints instead of only entry points
- `src/platform_context_graph/tools/languages/groovy.py`
  - expose the additional Jenkins metadata fields from the Groovy parser facade
- `src/platform_context_graph/query/repositories/content_enrichment_workflows.py`
  - keep controller evidence extraction for GitHub Actions and Jenkins in one place, and add shell-wrapper/controller hints that can feed automation-path assembly
- `src/platform_context_graph/query/repositories/content_enrichment_delivery_paths.py`
  - teach delivery-path derivation to merge controller-driven automation paths with existing GitHub Actions, GitOps, and Terraform/ECS/EKS path summaries
- `src/platform_context_graph/query/repositories/content_enrichment.py`
  - wire the new automation-path enrichment into repository context generation
- `src/platform_context_graph/query/repositories/content_enrichment_support.py`
  - add shared helpers for reading YAML, shell wrappers, ordered dedupe, and cross-repo correlation
- `src/platform_context_graph/mcp/tools/handlers/ecosystem_support_overview.py`
  - incorporate controller-driven automation signals into `deployment_story` and `topology_story`
- `src/platform_context_graph/mcp/tools/handlers/ecosystem_support_overview_story.py`
  - keep story ordering and fallback logic centralized and documented in code
- `docs/docs/reference/relationship-mapping.md`
  - document the controller -> automation -> runtime extension order and what evidence each stage owns
- `src/platform_context_graph/relationships/README.md`
  - document maintainer rules for adding new controller-driven automation paths safely
- `docs/docs/languages/groovy.md`
  - update Groovy/Jenkins capability docs to cover controller and automation hints, not just pipeline entry metadata
- `docs/docs/guides/mcp-guide.md`
  - document how `story`, `delivery_paths`, and controller-driven automation evidence should be consumed

### New files to create

- `src/platform_context_graph/query/repositories/content_enrichment_ansible.py`
  - extract high-signal automation evidence from playbooks, dynamic inventory, shell wrappers, `group_vars`, `host_vars`, and targeted role task entrypoints
- `src/platform_context_graph/query/repositories/content_enrichment_automation_paths.py`
  - assemble normalized `controller_driven_paths` from Jenkins, shell-wrapper, Ansible, Terraform, and runtime-family hints
- `src/platform_context_graph/tools/runtime_automation_families.py`
  - define generic runtime-family hints for controller-driven automation paths such as `wordpress_website_fleet`, `php_web_platform`, `ecs_service`, and `kubernetes_gitops`
- `tests/unit/query/test_repository_automation_paths.py`
  - unit coverage for controller-driven path assembly and ranking
- `tests/unit/query/test_repository_ansible_enrichment.py`
  - unit coverage for Ansible playbook, inventory, vars, and role-entry extraction
- `tests/fixtures/ecosystems/ansible_jenkins_automation/`
  - portable fixture corpus with Jenkins Groovy, shell-wrapper, playbook, inventory, vars, and WordPress/PHP runtime hints

## Chunk 1: Controller and Automation Evidence

### Task 1: Add a portable Jenkins + Ansible fixture corpus

**Files:**
- Create: `tests/fixtures/ecosystems/ansible_jenkins_automation/Jenkinsfile`
- Create: `tests/fixtures/ecosystems/ansible_jenkins_automation/scripts/deploy.sh`
- Create: `tests/fixtures/ecosystems/ansible_jenkins_automation/deploy.yml`
- Create: `tests/fixtures/ecosystems/ansible_jenkins_automation/inventory/dynamic_hosts.py`
- Create: `tests/fixtures/ecosystems/ansible_jenkins_automation/group_vars/all.yml`
- Create: `tests/fixtures/ecosystems/ansible_jenkins_automation/host_vars/web-prod.yml`
- Create: `tests/fixtures/ecosystems/ansible_jenkins_automation/roles/website_import/tasks/main.yml`
- Test: `tests/unit/query/test_repository_ansible_enrichment.py`
- Test: `tests/unit/query/test_repository_automation_paths.py`

- [ ] **Step 1: Write the failing fixture-driven tests**

```python
def test_extract_ansible_automation_evidence_recognizes_playbook_inventory_and_vars(
    fixture_repo: Path,
) -> None:
    evidence = extract_ansible_automation_evidence(fixture_repo)
    assert evidence["playbooks"][0]["relative_path"] == "deploy.yml"
    assert evidence["inventory_targets"][0]["group"] == "mws"
    assert evidence["runtime_hints"] == ["wordpress_website_fleet", "php_web_platform"]


def test_build_controller_driven_paths_combines_jenkins_ansible_and_runtime_hints() -> None:
    paths = build_controller_driven_paths(
        workflow_hints={
            "jenkins": [{"relative_path": "Jenkinsfile", "pipeline_calls": ["pipelineDeploy"]}]
        },
        ansible_hints={
            "playbooks": [{"relative_path": "deploy.yml", "hosts": ["mws"]}],
            "inventory_targets": [{"group": "mws", "environment": "prod"}],
            "runtime_hints": ["wordpress_website_fleet"],
        },
        platforms=[],
        provisioned_by=["terraform-stack-mws"],
    )
    assert paths[0]["controller_kind"] == "jenkins"
    assert paths[0]["automation_kind"] == "ansible"
    assert paths[0]["runtime_family"] == "wordpress_website_fleet"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/query/test_repository_ansible_enrichment.py tests/unit/query/test_repository_automation_paths.py -q`

Expected: FAIL with missing modules, missing fixture files, or missing automation-path assembly.

- [ ] **Step 3: Create the portable fixture corpus**

```yaml
# deploy.yml
- name: Configure websites
  hosts: mws
  roles:
    - { role: nginx, tags: ['nginx'] }
    - { role: php, tags: ['php'] }
    - { role: portal-websites, tags: ['deploy-portal'] }
```

```bash
# scripts/deploy.sh
#!/usr/bin/env bash
set -euo pipefail
ENVIRONMENT="${ENVIRONMENT:-jenkins}"
ansible-playbook deploy.yml -i inventory/dynamic_hosts.py --limit "${TARGET_ENV:-prod}"
```

- [ ] **Step 4: Re-run the failing tests to verify the fixtures load but the implementation is still missing**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/query/test_repository_ansible_enrichment.py tests/unit/query/test_repository_automation_paths.py -q`

Expected: FAIL with missing extraction helpers, not missing fixture files.

- [ ] **Step 5: Commit the fixture foundation**

```bash
git add tests/fixtures/ecosystems/ansible_jenkins_automation \
  tests/unit/query/test_repository_ansible_enrichment.py \
  tests/unit/query/test_repository_automation_paths.py
git commit -m "test: add Jenkins and Ansible automation fixtures"
```

### Task 2: Expand Groovy and Jenkins controller evidence

**Files:**
- Modify: `src/platform_context_graph/tools/languages/groovy_support.py`
- Modify: `src/platform_context_graph/tools/languages/groovy.py`
- Modify: `src/platform_context_graph/query/repositories/content_enrichment_workflows.py`
- Test: `tests/unit/parsers/test_groovy_parser.py`
- Test: `tests/unit/query/test_repository_automation_paths.py`

- [ ] **Step 1: Write the failing Jenkins metadata tests**

```python
def test_parse_jenkinsfile_extracts_ansible_and_shell_hints(tmp_path: Path) -> None:
    file_path = tmp_path / "Jenkinsfile"
    file_path.write_text(
        "@Library('pipelines') _\\n"
        "pipelineDeploy(entry_point: 'deploy.sh')\\n"
        "sh 'ansible-playbook deploy.yml -i inventory/dynamic_hosts.py --limit prod'\\n",
        encoding="utf-8",
    )
    result = _parser().parse(file_path)
    assert result["pipeline_calls"] == ["pipelineDeploy"]
    assert result["shell_commands"] == [
        "ansible-playbook deploy.yml -i inventory/dynamic_hosts.py --limit prod"
    ]
    assert result["ansible_playbook_hints"][0]["playbook"] == "deploy.yml"
```

- [ ] **Step 2: Run the parser test to verify it fails**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/parsers/test_groovy_parser.py::test_parse_jenkinsfile_extracts_ansible_and_shell_hints -q`

Expected: FAIL because `shell_commands` and `ansible_playbook_hints` are not extracted yet.

- [ ] **Step 3: Implement the Jenkins controller hints**

```python
_SHELL_COMMAND_RE = re.compile(r"sh\\s+['\\\"]([^'\\\"]+)['\\\"]")
_ANSIBLE_PLAYBOOK_RE = re.compile(
    r"ansible-playbook\\s+(?P<playbook>[^\\s]+)(?:.*?-i\\s+(?P<inventory>[^\\s]+))?"
)

def extract_jenkins_pipeline_metadata(source_text: str) -> dict[str, Any]:
    shell_commands = _ordered_unique(_SHELL_COMMAND_RE.findall(source_text))
    ansible_hints = []
    for command in shell_commands:
        match = _ANSIBLE_PLAYBOOK_RE.search(command)
        if match is None:
            continue
        ansible_hints.append(
            {
                "playbook": match.group("playbook"),
                "inventory": match.group("inventory"),
                "command": command,
            }
        )
    return {
        ...,
        "shell_commands": shell_commands,
        "ansible_playbook_hints": ansible_hints,
    }
```

- [ ] **Step 4: Teach workflow enrichment to preserve Jenkins controller hints**

```python
jenkins.append(
    {
        "relative_path": str(relative_path),
        "shared_libraries": parsed["shared_libraries"],
        "pipeline_calls": parsed["pipeline_calls"],
        "shell_commands": parsed["shell_commands"],
        "ansible_playbook_hints": parsed["ansible_playbook_hints"],
    }
)
```

- [ ] **Step 5: Run the parser and workflow-focused tests**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/parsers/test_groovy_parser.py tests/unit/query/test_repository_automation_paths.py -q`

Expected: PASS

- [ ] **Step 6: Commit the controller evidence slice**

```bash
git add src/platform_context_graph/tools/languages/groovy_support.py \
  src/platform_context_graph/tools/languages/groovy.py \
  src/platform_context_graph/query/repositories/content_enrichment_workflows.py \
  tests/unit/parsers/test_groovy_parser.py \
  tests/unit/query/test_repository_automation_paths.py
git commit -m "feat: extract Jenkins controller hints"
```

### Task 3: Add high-signal Ansible enrichment and runtime-family hints

**Files:**
- Create: `src/platform_context_graph/query/repositories/content_enrichment_ansible.py`
- Create: `src/platform_context_graph/tools/runtime_automation_families.py`
- Modify: `src/platform_context_graph/query/repositories/content_enrichment_support.py`
- Test: `tests/unit/query/test_repository_ansible_enrichment.py`

- [ ] **Step 1: Write the failing Ansible extraction tests**

```python
def test_extract_ansible_automation_evidence_reads_playbooks_and_dynamic_inventory(
    fixture_repo: Path,
) -> None:
    evidence = extract_ansible_automation_evidence(fixture_repo)
    assert evidence["playbooks"] == [
        {
            "relative_path": "deploy.yml",
            "hosts": ["mws"],
            "roles": ["nginx", "php", "portal-websites"],
            "tags": ["deploy-portal", "nginx", "php"],
        }
    ]
    assert evidence["inventory_targets"][0]["environment"] == "prod"


def test_infer_automation_runtime_families_prefers_wordpress_over_generic_php() -> None:
    assert infer_automation_runtime_families(
        [
            "wp --allow-root db import dump.sql",
            "wp-content/uploads",
            "nginx",
            "php",
        ]
    ) == ["wordpress_website_fleet", "php_web_platform"]
```

- [ ] **Step 2: Run the Ansible tests to verify they fail**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/query/test_repository_ansible_enrichment.py -q`

Expected: FAIL with missing extraction helpers and runtime-family inference.

- [ ] **Step 3: Implement the high-signal Ansible extraction**

```python
def extract_ansible_automation_evidence(repo_root: Path) -> dict[str, Any]:
    return {
        "playbooks": _extract_top_level_playbooks(repo_root),
        "inventory_targets": _extract_inventory_targets(repo_root),
        "group_vars": _extract_yaml_var_sets(repo_root / "group_vars"),
        "host_vars": _extract_yaml_var_sets(repo_root / "host_vars"),
        "shell_wrappers": _extract_ansible_shell_wrappers(repo_root),
        "runtime_hints": infer_automation_runtime_families(_collect_runtime_signals(repo_root)),
        "role_entrypoints": _extract_role_task_entrypoints(repo_root),
    }
```

- [ ] **Step 4: Keep the runtime-family seam generic**

```python
@dataclass(frozen=True, slots=True)
class AutomationRuntimeFamily:
    kind: str
    display_name: str
    signal_patterns: tuple[str, ...]

_AUTOMATION_RUNTIME_FAMILIES = (
    AutomationRuntimeFamily(
        kind="wordpress_website_fleet",
        display_name="WordPress website fleet",
        signal_patterns=("wp --allow-root", "wp-content/uploads", "portal-configs"),
    ),
    AutomationRuntimeFamily(
        kind="php_web_platform",
        display_name="PHP web platform",
        signal_patterns=("nginx", "php", "memcached"),
    ),
)
```

- [ ] **Step 5: Run the Ansible extraction tests**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/query/test_repository_ansible_enrichment.py -q`

Expected: PASS

- [ ] **Step 6: Commit the Ansible enrichment slice**

```bash
git add src/platform_context_graph/query/repositories/content_enrichment_ansible.py \
  src/platform_context_graph/tools/runtime_automation_families.py \
  src/platform_context_graph/query/repositories/content_enrichment_support.py \
  tests/unit/query/test_repository_ansible_enrichment.py
git commit -m "feat: extract Ansible automation evidence"
```

## Chunk 2: Path Assembly, MCP Stories, Docs, and Acceptance

### Task 4: Assemble normalized controller-driven automation paths

**Files:**
- Create: `src/platform_context_graph/query/repositories/content_enrichment_automation_paths.py`
- Modify: `src/platform_context_graph/query/repositories/content_enrichment.py`
- Modify: `src/platform_context_graph/query/repositories/content_enrichment_delivery_paths.py`
- Test: `tests/unit/query/test_repository_automation_paths.py`
- Test: `tests/unit/query/test_repository_content_enrichment.py`

- [ ] **Step 1: Write the failing automation-path assembly tests**

```python
def test_build_controller_driven_paths_emits_generic_controller_automation_runtime_shape() -> None:
    paths = build_controller_driven_paths(
        workflow_hints={
            "jenkins": [
                {
                    "relative_path": "Jenkinsfile",
                    "pipeline_calls": ["pipelineDeploy"],
                    "ansible_playbook_hints": [{"playbook": "deploy.yml", "inventory": "inventory/dynamic_hosts.py"}],
                }
            ]
        },
        ansible_hints={
            "playbooks": [{"relative_path": "deploy.yml", "hosts": ["mws"]}],
            "inventory_targets": [{"group": "mws", "environment": "prod"}],
            "runtime_hints": ["wordpress_website_fleet"],
        },
        platforms=[],
        provisioned_by=["terraform-stack-mws"],
    )
    assert paths == [
        {
            "controller_kind": "jenkins",
            "automation_kind": "ansible",
            "runtime_family": "wordpress_website_fleet",
            "confidence": "high",
            ...
        }
    ]
```

- [ ] **Step 2: Run the assembly tests to verify they fail**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/query/test_repository_automation_paths.py tests/unit/query/test_repository_content_enrichment.py -q`

Expected: FAIL because `controller_driven_paths` are not yet assembled or wired into enriched context.

- [ ] **Step 3: Implement normalized path assembly**

```python
def build_controller_driven_paths(
    *,
    workflow_hints: dict[str, Any],
    ansible_hints: dict[str, Any],
    platforms: list[dict[str, Any]],
    provisioned_by: list[str],
) -> list[dict[str, Any]]:
    if not workflow_hints.get("jenkins") or not ansible_hints.get("playbooks"):
        return []
    runtime_family = first_or_none(ansible_hints.get("runtime_hints") or [])
    return [
        {
            "controller_kind": "jenkins",
            "controller_repository": None,
            "automation_kind": "ansible",
            "automation_repository": None,
            "entry_points": _entry_points_from_hints(...),
            "target_descriptors": _target_descriptors_from_inventory(...),
            "runtime_family": runtime_family,
            "supporting_repositories": provisioned_by,
            "confidence": "high" if runtime_family else "medium",
            "explanation": _format_controller_path_explanation(...),
        }
    ]
```

- [ ] **Step 4: Feed controller-driven paths into delivery paths and enriched context**

```python
ansible_hints = extract_ansible_automation_evidence(repo_root)
context["controller_driven_paths"] = build_controller_driven_paths(
    workflow_hints=delivery_workflows,
    ansible_hints=ansible_hints,
    platforms=list(context.get("platforms") or []),
    provisioned_by=list(context.get("provisioned_by") or []),
)
delivery_paths = summarize_delivery_paths(
    ...,
    controller_driven_paths=context["controller_driven_paths"],
)
```

- [ ] **Step 5: Run the assembly and enrichment tests**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/query/test_repository_automation_paths.py tests/unit/query/test_repository_content_enrichment.py -q`

Expected: PASS

- [ ] **Step 6: Commit the automation-path assembly**

```bash
git add src/platform_context_graph/query/repositories/content_enrichment_automation_paths.py \
  src/platform_context_graph/query/repositories/content_enrichment.py \
  src/platform_context_graph/query/repositories/content_enrichment_delivery_paths.py \
  tests/unit/query/test_repository_automation_paths.py \
  tests/unit/query/test_repository_content_enrichment.py
git commit -m "feat: assemble controller-driven automation paths"
```

### Task 5: Use controller-driven paths in MCP stories and fallbacks

**Files:**
- Modify: `src/platform_context_graph/mcp/tools/handlers/ecosystem_support_overview.py`
- Modify: `src/platform_context_graph/mcp/tools/handlers/ecosystem_support_overview_story.py`
- Modify: `src/platform_context_graph/mcp/tools/handlers/ecosystem.py`
- Test: `tests/unit/handlers/test_ecosystem_support_overview.py`
- Test: `tests/unit/handlers/test_repo_context.py`
- Test: `tests/integration/mcp/test_repository_runtime_context.py`

- [ ] **Step 1: Write the failing story tests**

```python
def test_deployment_story_prefers_controller_driven_path_for_ansible_repos() -> None:
    context = {
        "controller_driven_paths": [
            {
                "controller_kind": "jenkins",
                "automation_kind": "ansible",
                "runtime_family": "wordpress_website_fleet",
                "target_descriptors": ["prod", "qa"],
                "supporting_repositories": ["terraform-stack-mws"],
                "explanation": "Jenkins runs Ansible to operate a WordPress website fleet.",
            }
        ],
        "delivery_paths": [],
        "platforms": [],
    }
    overview = build_deployment_overview(context)
    assert overview["deployment_story"][0].startswith("Jenkins runs Ansible")
```

- [ ] **Step 2: Run the story tests to verify they fail**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/unit/handlers/test_ecosystem_support_overview.py tests/unit/handlers/test_repo_context.py -q`

Expected: FAIL because controller-driven paths are not yet used by story ordering.

- [ ] **Step 3: Implement the controller-driven story fallback**

```python
if controller_paths:
    deployment_story.append(controller_paths[0]["explanation"])
    if controller_paths[0]["supporting_repositories"]:
        deployment_story.append(
            "Supporting infrastructure comes from "
            + ", ".join(controller_paths[0]["supporting_repositories"])
            + "."
        )
```

- [ ] **Step 4: Keep the top-level MCP `story` field aligned**

Run: `PYTHONPATH=src uv run --extra dev python -m pytest tests/integration/mcp/test_repository_runtime_context.py -q`

Expected: PASS with `story` preferring the controller-driven automation narrative when that is the strongest evidence.

- [ ] **Step 5: Commit the story integration**

```bash
git add src/platform_context_graph/mcp/tools/handlers/ecosystem_support_overview.py \
  src/platform_context_graph/mcp/tools/handlers/ecosystem_support_overview_story.py \
  src/platform_context_graph/mcp/tools/handlers/ecosystem.py \
  tests/unit/handlers/test_ecosystem_support_overview.py \
  tests/unit/handlers/test_repo_context.py \
  tests/integration/mcp/test_repository_runtime_context.py
git commit -m "feat: surface controller-driven automation stories"
```

### Task 6: Document the extension order and run acceptance

**Files:**
- Modify: `docs/docs/reference/relationship-mapping.md`
- Modify: `src/platform_context_graph/relationships/README.md`
- Modify: `docs/docs/languages/groovy.md`
- Modify: `docs/docs/guides/mcp-guide.md`

- [ ] **Step 1: Update the mapping and maintainer docs**

Document:

- the `controller -> automation -> runtime` flow
- the investment order for Jenkins and Ansible surfaces
- why runtime families stay generic
- what belongs in canonical relationships versus read-side story enrichment
- how to extend this for other controller families and runtimes

- [ ] **Step 2: Update Groovy and MCP consumer docs**

Document:

- new Jenkins metadata fields
- that `story` may now come from controller-driven automation evidence
- that callers should prefer `story` first, then `delivery_paths`, then raw details

- [ ] **Step 3: Run the targeted verification suite**

Run:

```bash
uv run python scripts/check_python_docstrings.py
uv run python scripts/check_python_file_lengths.py
PYTHONPATH=src uv run --extra dev python -m pytest \
  tests/unit/parsers/test_groovy_parser.py \
  tests/unit/query/test_repository_ansible_enrichment.py \
  tests/unit/query/test_repository_automation_paths.py \
  tests/unit/query/test_repository_content_enrichment.py \
  tests/unit/handlers/test_ecosystem_support_overview.py \
  tests/unit/handlers/test_repo_context.py \
  tests/integration/mcp/test_repository_runtime_context.py -q
uvx --with mkdocs-material mkdocs build -f docs/mkdocs.yml
```

Expected: PASS

- [ ] **Step 4: Run one real acceptance pass against MWS repos**

Validate that a repo summary or deployment trace for the MWS family can now
truthfully say:

- Jenkins drives the workflow
- Ansible executes the automation
- runtime hints point to a WordPress/PHP website platform
- Terraform repos appear only as supporting infrastructure where the evidence is direct

- [ ] **Step 5: Commit the documentation and acceptance slice**

```bash
git add docs/docs/reference/relationship-mapping.md \
  src/platform_context_graph/relationships/README.md \
  docs/docs/languages/groovy.md \
  docs/docs/guides/mcp-guide.md
git commit -m "docs: add controller-driven automation mapping guidance"
```
