from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from platform_context_graph.query.repositories.content_enrichment_ansible import (
    extract_ansible_automation_evidence,
)
from platform_context_graph.query.repositories.content_enrichment_automation_paths import (
    build_controller_driven_paths,
)
from platform_context_graph.query.repositories.content_enrichment_workflows import (
    extract_delivery_workflows,
)
from platform_context_graph.parsers.languages.groovy_support import (
    extract_jenkins_pipeline_metadata,
)

_SENTINEL_DB = object()
_SENTINEL_REPO_ID = "repository:r_fixture"


def _make_fs_discovery_mocks(
    repo_root: Path,
    repo_id: str = _SENTINEL_REPO_ID,
) -> dict[str, Any]:
    """Build mock functions that serve indexed_file_discovery from a local dir."""

    all_files = sorted(
        str(p.relative_to(repo_root)) for p in repo_root.rglob("*") if p.is_file()
    )

    def discover_repo_files(
        _database: Any,
        rid: str,
        *,
        prefix: str | None = None,
        suffix: str | None = None,
        pattern: str | None = None,
    ) -> list[str]:
        if rid != repo_id:
            return []
        results = list(all_files)
        if prefix:
            results = [f for f in results if f.startswith(prefix)]
        if suffix:
            results = [f for f in results if f.endswith(suffix)]
        if pattern:
            regex = re.compile(pattern)
            results = [f for f in results if regex.search(f)]
        return sorted(results)

    def read_file_content(_database: Any, rid: str, relative_path: str) -> str | None:
        if rid != repo_id:
            return None
        path = repo_root / relative_path
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8", errors="ignore")

    def read_yaml_file(_database: Any, rid: str, relative_path: str) -> dict | None:
        content = read_file_content(_database, rid, relative_path)
        if content is None:
            return None
        try:
            parsed = yaml.safe_load(content)
        except yaml.YAMLError:
            return None
        return parsed if isinstance(parsed, dict) else None

    return {
        "discover_repo_files": discover_repo_files,
        "read_file_content": read_file_content,
        "read_yaml_file": read_yaml_file,
    }


def _patch_indexed_discovery(
    monkeypatch, repo_root: Path, repo_id: str = _SENTINEL_REPO_ID
):
    """Monkeypatch indexed_file_discovery in content_enrichment_workflows."""

    mocks = _make_fs_discovery_mocks(repo_root, repo_id)
    mod = "platform_context_graph.query.repositories.content_enrichment_workflows"
    monkeypatch.setattr(f"{mod}.discover_repo_files", mocks["discover_repo_files"])
    monkeypatch.setattr(f"{mod}.read_file_content", mocks["read_file_content"])
    monkeypatch.setattr(f"{mod}.read_yaml_file", mocks["read_yaml_file"])


def _fixture_controller_hints(
    fixture_repo: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    """Build expected controller hints from the fixture repo for assertions."""

    jenkinsfile_path = fixture_repo / "Jenkinsfile"
    playbook_path = fixture_repo / "deploy.yml"
    group_vars_path = fixture_repo / "group_vars" / "all.yml"
    host_vars_path = fixture_repo / "host_vars" / "web-prod.yml"

    jenkins_metadata = extract_jenkins_pipeline_metadata(
        jenkinsfile_path.read_text(encoding="utf-8")
    )
    playbook = yaml.safe_load(playbook_path.read_text(encoding="utf-8"))
    group_vars = yaml.safe_load(group_vars_path.read_text(encoding="utf-8"))
    host_vars = yaml.safe_load(host_vars_path.read_text(encoding="utf-8"))

    assert isinstance(playbook, list) and playbook
    assert isinstance(group_vars, dict)
    assert isinstance(host_vars, dict)

    return (
        jenkins_metadata,
        {
            "playbooks": [
                {
                    "relative_path": str(playbook_path.relative_to(fixture_repo)),
                    "hosts": [str(playbook[0]["hosts"])],
                }
            ],
            "inventory_targets": [
                {
                    "group": str(playbook[0]["hosts"]),
                    "environment": str(host_vars["environment"]),
                }
            ],
            "runtime_hints": list(group_vars["runtime_hints"]),
        },
    )


def test_build_controller_driven_paths_combines_jenkins_ansible_and_runtime_hints(
    monkeypatch,
    fixture_repo: Path,
) -> None:
    """Verify Jenkins metadata is extracted through indexed discovery."""

    _patch_indexed_discovery(monkeypatch, fixture_repo)
    jenkins_metadata, ansible_hints = _fixture_controller_hints(fixture_repo)
    delivery_workflows = extract_delivery_workflows(
        repository={"id": _SENTINEL_REPO_ID, "local_path": str(fixture_repo)},
        resolve_repository=lambda _ref: None,
        database=_SENTINEL_DB,
    )
    workflow_hints = delivery_workflows["jenkins"]
    assert workflow_hints[0]["relative_path"] == "Jenkinsfile"
    assert workflow_hints[0]["pipeline_calls"] == jenkins_metadata["pipeline_calls"]
    assert workflow_hints[0]["shell_commands"] == jenkins_metadata["shell_commands"]
    assert (
        workflow_hints[0]["ansible_playbook_hints"]
        == jenkins_metadata["ansible_playbook_hints"]
    )
    assert ansible_hints["playbooks"][0]["relative_path"] == "deploy.yml"
    assert ansible_hints["runtime_hints"] == [
        "wordpress_website_fleet",
        "php_web_platform",
    ]


def test_build_controller_driven_paths_emits_generic_controller_automation_runtime_shape() -> (
    None
):
    """Verify controller-driven path shape without database dependency."""

    paths = build_controller_driven_paths(
        workflow_hints={
            "jenkins": [
                {
                    "relative_path": "Jenkinsfile",
                    "pipeline_calls": ["pipelineDeploy"],
                    "ansible_playbook_hints": [
                        {
                            "playbook": "deploy.yml",
                            "inventory": "inventory/dynamic_hosts.py",
                        }
                    ],
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
            "controller_repository": None,
            "automation_kind": "ansible",
            "automation_repository": None,
            "entry_points": ["deploy.yml"],
            "target_descriptors": ["mws", "prod"],
            "runtime_family": "wordpress_website_fleet",
            "supporting_repositories": ["terraform-stack-mws"],
            "confidence": "high",
            "explanation": (
                "jenkins controller Jenkinsfile invokes ansible entry points "
                "deploy.yml targeting mws, prod for wordpress_website_fleet "
                "with support from terraform-stack-mws."
            ),
        }
    ]


def test_build_controller_driven_paths_resolves_ansible_entry_points_from_jenkins_shell_wrappers(
    monkeypatch,
    fixture_repo: Path,
) -> None:
    """Verify shell-wrapper based ansible entry points are resolved."""

    _patch_indexed_discovery(monkeypatch, fixture_repo)
    delivery_workflows = extract_delivery_workflows(
        repository={"id": _SENTINEL_REPO_ID, "local_path": str(fixture_repo)},
        resolve_repository=lambda _ref: None,
        database=_SENTINEL_DB,
    )
    ansible_hints = extract_ansible_automation_evidence(fixture_repo)

    assert delivery_workflows["jenkins"][0]["ansible_playbook_hints"] == []
    assert ansible_hints["shell_wrappers"] == [
        {
            "relative_path": "scripts/deploy.sh",
            "commands": ["ansible-playbook deploy.yml -i inventory/dynamic_hosts.py"],
            "playbooks": ["deploy.yml"],
            "inventories": ["inventory/dynamic_hosts.py"],
        }
    ]

    assert build_controller_driven_paths(
        workflow_hints=delivery_workflows,
        ansible_hints=ansible_hints,
        platforms=[],
        provisioned_by=[{"name": "terraform-stack-mws"}],
    ) == [
        {
            "controller_kind": "jenkins",
            "controller_repository": None,
            "automation_kind": "ansible",
            "automation_repository": None,
            "entry_points": ["deploy.yml"],
            "target_descriptors": ["mws", "prod"],
            "runtime_family": "wordpress_website_fleet",
            "supporting_repositories": ["terraform-stack-mws"],
            "confidence": "high",
            "explanation": (
                "jenkins controller Jenkinsfile invokes ansible entry points "
                "deploy.yml targeting mws, prod for wordpress_website_fleet "
                "with support from terraform-stack-mws."
            ),
        }
    ]


def test_build_controller_driven_paths_supports_nested_jenkins_groovy_entrypoints(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Verify nested Groovy helpers under roles/ are discovered via index."""

    repo_root = tmp_path / "automation-repo"
    (repo_root / "roles" / "websites_list").mkdir(parents=True)
    (repo_root / "group_vars").mkdir()
    (repo_root / "host_vars").mkdir()
    (repo_root / "roles" / "websites_list" / "jenkins.groovy").write_text(
        "// Jenkins helper script used to retrieve website inventory\n",
        encoding="utf-8",
    )
    (repo_root / "deploy.yml").write_text(
        "- hosts: mws\n  roles:\n    - portal-websites\n",
        encoding="utf-8",
    )
    (repo_root / "group_vars" / "all.yml").write_text(
        "runtime_hints:\n  - wordpress_website_fleet\n",
        encoding="utf-8",
    )
    (repo_root / "host_vars" / "prod.yml").write_text(
        "environment: prod\n",
        encoding="utf-8",
    )

    _patch_indexed_discovery(monkeypatch, repo_root)
    delivery_workflows = extract_delivery_workflows(
        repository={"id": _SENTINEL_REPO_ID, "local_path": str(repo_root)},
        resolve_repository=lambda _ref: None,
        database=_SENTINEL_DB,
    )
    ansible_hints = extract_ansible_automation_evidence(repo_root)

    assert build_controller_driven_paths(
        workflow_hints=delivery_workflows,
        ansible_hints=ansible_hints,
        platforms=[],
        provisioned_by=["terraform-stack-mws"],
    ) == [
        {
            "controller_kind": "jenkins",
            "controller_repository": None,
            "automation_kind": "ansible",
            "automation_repository": None,
            "entry_points": ["deploy.yml"],
            "target_descriptors": ["mws", "prod"],
            "runtime_family": "wordpress_website_fleet",
            "supporting_repositories": ["terraform-stack-mws"],
            "confidence": "high",
            "explanation": (
                "jenkins controller roles/websites_list/jenkins.groovy invokes "
                "ansible entry points deploy.yml targeting mws, prod for "
                "wordpress_website_fleet with support from terraform-stack-mws."
            ),
        }
    ]
