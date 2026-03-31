"""Fast fixture-corpus evidence checks for the synthetic relationship platform."""

from __future__ import annotations

import shutil
from pathlib import Path

from platform_context_graph.relationships.execution import build_repository_checkouts
from platform_context_graph.relationships.file_evidence import (
    discover_checkout_file_evidence,
)

_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "relationship_platform"
)


def test_relationship_platform_fixture_corpus_emits_expected_file_evidence(
    tmp_path: Path,
) -> None:
    """The synthetic corpus should exercise the main raw file evidence extractors."""

    staged_repos: list[Path] = []
    for repo_path in sorted(path for path in _FIXTURE_ROOT.iterdir() if path.is_dir()):
        staged_path = tmp_path / repo_path.name
        shutil.copytree(repo_path, staged_path)
        staged_repos.append(staged_path)

    checkouts = build_repository_checkouts(staged_repos)
    repo_ids_by_name = {
        checkout.repo_name: checkout.logical_repo_id for checkout in checkouts
    }
    evidence = discover_checkout_file_evidence(checkouts)
    evidence_pairs = {
        (
            item.relationship_type,
            item.source_repo_id,
            item.target_repo_id,
            item.target_entity_id,
        )
        for item in evidence
    }

    assert (
        "DISCOVERS_CONFIG_IN",
        repo_ids_by_name["delivery-argocd"],
        repo_ids_by_name["deployment-kustomize"],
        None,
    ) in evidence_pairs
    assert (
        "DEPLOYS_FROM",
        repo_ids_by_name["service-edge-api"],
        repo_ids_by_name["deployment-helm"],
        None,
    ) in evidence_pairs
    assert (
        "PROVISIONS_DEPENDENCY_FOR",
        repo_ids_by_name["infra-runtime-modern"],
        repo_ids_by_name["service-worker-jobs"],
        None,
    ) in evidence_pairs
    assert (
        "PROVISIONS_PLATFORM",
        repo_ids_by_name["infra-runtime-legacy"],
        None,
        "platform:ecs:aws:cluster/legacy-edge:none:none",
    ) in evidence_pairs
    assert (
        "RUNS_ON",
        repo_ids_by_name["service-edge-api"],
        None,
        "platform:ecs:aws:cluster/legacy-edge:none:none",
    ) in evidence_pairs
