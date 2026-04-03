from __future__ import annotations

from pathlib import Path


from platform_context_graph.platform.automation_families import (
    infer_automation_runtime_families,
)


def test_extract_ansible_automation_evidence_reads_playbooks_and_dynamic_inventory(
    fixture_repo: Path,
) -> None:
    assert (fixture_repo / "deploy.yml").exists()

    from platform_context_graph.query.repositories.content_enrichment_ansible import (
        extract_ansible_automation_evidence,
    )

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
    assert evidence["runtime_hints"] == [
        "wordpress_website_fleet",
        "php_web_platform",
    ]


def test_infer_automation_runtime_families_prefers_wordpress_over_generic_php() -> None:
    assert infer_automation_runtime_families(
        [
            "wp --allow-root db import dump.sql",
            "wp-content/uploads",
            "nginx",
            "php",
        ]
    ) == ["wordpress_website_fleet", "php_web_platform"]
