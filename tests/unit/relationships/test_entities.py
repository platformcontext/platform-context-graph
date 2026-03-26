"""Unit tests for canonical relationship entities."""

from __future__ import annotations

from platform_context_graph.relationships.entities import (
    CanonicalEntity,
    PlatformEntity,
    WorkloadSubjectEntity,
    canonical_platform_id,
)


def test_canonical_platform_id_requires_stable_discriminator() -> None:
    """Platform candidates without a stable discriminator must stay non-canonical."""

    assert (
        canonical_platform_id(
            kind="eks",
            provider="aws",
            name=None,
            environment=None,
            region=None,
            locator=None,
        )
        is None
    )


def test_canonical_platform_id_prefers_locator_over_name() -> None:
    """Locator should win over name when building a canonical platform id."""

    assert (
        canonical_platform_id(
            kind="ecs",
            provider="aws",
            name="ignored-name",
            environment="prod",
            region="us-east-1",
            locator="arn:aws:ecs:us-east-1:123456789012:cluster/node10",
        )
        == "platform:ecs:aws:arn:aws:ecs:us-east-1:123456789012:cluster/node10:prod:us-east-1"
    )


def test_workload_subject_id_normalizes_repo_type_name_environment_and_path() -> None:
    """Workload subject ids should normalize repo, type, name, env, and path."""

    entity = WorkloadSubjectEntity.from_parts(
        repository_id="repository:r_1234abcd",
        subject_type="addon",
        name="Grafana",
        environment="ops-qa",
        path="argocd/grafana/overlays/ops-qa",
    )

    assert entity.entity_id == (
        "workload-subject:repository:r_1234abcd:addon:grafana:ops-qa:"
        "argocd/grafana/overlays/ops-qa"
    )
