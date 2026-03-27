from __future__ import annotations

from pathlib import Path

from platform_context_graph.query.repositories.content_enrichment_ansible import (
    extract_ansible_automation_evidence,
)


def test_extract_ansible_automation_evidence_recognizes_playbook_inventory_and_vars(
    fixture_repo: Path,
) -> None:
    evidence = extract_ansible_automation_evidence(fixture_repo)
    assert evidence["playbooks"][0]["relative_path"] == "deploy.yml"
    assert evidence["inventory_targets"][0]["group"] == "mws"
    assert evidence["runtime_hints"] == [
        "wordpress_website_fleet",
        "php_web_platform",
    ]
