from __future__ import annotations

from platform_context_graph.query.repositories.content_enrichment_automation_paths import (
    build_controller_driven_paths,
)


def test_build_controller_driven_paths_combines_jenkins_ansible_and_runtime_hints() -> None:
    paths = build_controller_driven_paths(
        workflow_hints={
            "jenkins": [
                {"relative_path": "Jenkinsfile", "pipeline_calls": ["pipelineDeploy"]}
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
    assert paths[0]["controller_kind"] == "jenkins"
    assert paths[0]["automation_kind"] == "ansible"
    assert paths[0]["runtime_family"] == "wordpress_website_fleet"
