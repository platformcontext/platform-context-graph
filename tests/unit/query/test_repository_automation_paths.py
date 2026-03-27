from __future__ import annotations

from pathlib import Path

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
from platform_context_graph.tools.languages.groovy_support import (
    extract_jenkins_pipeline_metadata,
)


def _fixture_controller_hints(
    fixture_repo: Path,
) -> tuple[dict[str, object], dict[str, object]]:
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
    fixture_repo: Path,
) -> None:
    jenkins_metadata, ansible_hints = _fixture_controller_hints(fixture_repo)
    delivery_workflows = extract_delivery_workflows(
        repository={"local_path": str(fixture_repo)},
        resolve_repository=lambda _ref: None,
    )
    workflow_hints = delivery_workflows["jenkins"]
    assert workflow_hints[0]["relative_path"] == "Jenkinsfile"
    assert workflow_hints[0]["pipeline_calls"] == jenkins_metadata["pipeline_calls"]
    assert workflow_hints[0]["shell_commands"] == jenkins_metadata["shell_commands"]
    assert workflow_hints[0]["ansible_playbook_hints"] == jenkins_metadata[
        "ansible_playbook_hints"
    ]
    assert ansible_hints["playbooks"][0]["relative_path"] == "deploy.yml"
    assert ansible_hints["runtime_hints"] == [
        "wordpress_website_fleet",
        "php_web_platform",
    ]


def test_build_controller_driven_paths_emits_generic_controller_automation_runtime_shape() -> (
    None
):
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
    fixture_repo: Path,
) -> None:
    delivery_workflows = extract_delivery_workflows(
        repository={"local_path": str(fixture_repo)},
        resolve_repository=lambda _ref: None,
    )
    ansible_hints = extract_ansible_automation_evidence(fixture_repo)

    assert delivery_workflows["jenkins"][0]["ansible_playbook_hints"] == []
    assert ansible_hints["shell_wrappers"] == [
        {
            "relative_path": "scripts/deploy.sh",
            "commands": [
                "ansible-playbook deploy.yml -i inventory/dynamic_hosts.py"
            ],
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
