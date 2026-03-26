"""Unit tests for canonical relationship entities."""

from __future__ import annotations

from platform_context_graph.repository_identity import (
    normalize_remote_url,
    repo_slug_from_remote_url,
)
from platform_context_graph.relationships.entities import (
    PlatformEntity,
    RepositoryEntity,
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


def test_workload_subject_id_preserves_case_in_path_discriminator() -> None:
    """Different path casing must remain distinct for workload subjects."""

    upper = WorkloadSubjectEntity.from_parts(
        repository_id="repository:r_1234abcd",
        subject_type="addon",
        name="Grafana",
        environment="ops-qa",
        path="Services/API",
    )
    lower = WorkloadSubjectEntity.from_parts(
        repository_id="repository:r_1234abcd",
        subject_type="addon",
        name="Grafana",
        environment="ops-qa",
        path="services/api",
    )

    assert upper.entity_id != lower.entity_id
    assert upper.entity_id.endswith(":Services/API")
    assert lower.entity_id.endswith(":services/api")


def test_repository_from_parts_normalizes_remote_identity_and_slug() -> None:
    """Equivalent remotes should converge on one canonical repository entity."""

    ssh_remote = "git@github.com:PlatformContext/platform-context-graph.git"
    https_remote = "https://github.com/platformcontext/platform-context-graph.git"
    expected_remote = normalize_remote_url(ssh_remote)
    expected_slug = repo_slug_from_remote_url(expected_remote)

    ssh_repo = RepositoryEntity.from_parts(
        name="platform-context-graph",
        remote_url=ssh_remote,
        local_path="/srv/repos/platform-context-graph",
    )
    https_repo = RepositoryEntity.from_parts(
        name="platform-context-graph",
        remote_url=https_remote,
        local_path="/tmp/other-checkout/platform-context-graph",
    )

    assert ssh_repo.entity_id == https_repo.entity_id
    assert ssh_repo.remote_url == expected_remote
    assert https_repo.remote_url == expected_remote
    assert ssh_repo.repo_slug == expected_slug
    assert https_repo.repo_slug == expected_slug
