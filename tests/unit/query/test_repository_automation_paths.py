from __future__ import annotations

from pathlib import Path

import yaml

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
        {
            "jenkins": [
                {
                    "relative_path": str(jenkinsfile_path.relative_to(fixture_repo)),
                    "pipeline_calls": jenkins_metadata["pipeline_calls"],
                }
            ]
        },
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
    workflow_hints, ansible_hints = _fixture_controller_hints(fixture_repo)
    assert workflow_hints["jenkins"][0]["relative_path"] == "Jenkinsfile"
    assert ansible_hints["playbooks"][0]["relative_path"] == "deploy.yml"
    assert ansible_hints["runtime_hints"] == [
        "wordpress_website_fleet",
        "php_web_platform",
    ]

    from platform_context_graph.query.repositories.content_enrichment_automation_paths import (
        build_controller_driven_paths,
    )

    paths = build_controller_driven_paths(
        workflow_hints=workflow_hints,
        ansible_hints=ansible_hints,
        platforms=[],
        provisioned_by=["terraform-stack-mws"],
    )
    assert paths[0]["controller_kind"] == "jenkins"
    assert paths[0]["automation_kind"] == "ansible"
    assert paths[0]["runtime_family"] == "wordpress_website_fleet"
