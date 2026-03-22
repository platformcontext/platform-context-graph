from __future__ import annotations

from platform_context_graph.repository_identity import (
    canonical_repository_id,
    normalize_remote_url,
    repo_slug_from_remote_url,
)


def test_normalize_remote_url_handles_ssh_https_and_tokenized_variants() -> None:
    ssh = "git@github.com:PlatformContext/platform-context-graph.git"
    https = "https://github.com/platformcontext/platform-context-graph.git"
    tokenized = "https://x-access-token:secret@github.com/platformcontext/platform-context-graph.git"

    assert (
        normalize_remote_url(ssh)
        == "https://github.com/platformcontext/platform-context-graph"
    )
    assert (
        normalize_remote_url(https)
        == "https://github.com/platformcontext/platform-context-graph"
    )
    assert (
        normalize_remote_url(tokenized)
        == "https://github.com/platformcontext/platform-context-graph"
    )


def test_canonical_repository_id_prefers_normalized_remote_identity() -> None:
    ssh_remote = "git@github.com:PlatformContext/platform-context-graph.git"
    https_remote = "https://github.com/platformcontext/platform-context-graph.git"

    ssh_id = canonical_repository_id(
        remote_url=ssh_remote,
        local_path="/srv/repos/platform-context-graph",
    )
    https_id = canonical_repository_id(
        remote_url=https_remote,
        local_path="/tmp/other-checkout/platform-context-graph",
    )

    assert ssh_id == https_id
    assert ssh_id.startswith("repository:r_")


def test_canonical_repository_id_falls_back_to_local_path_without_remote() -> None:
    first = canonical_repository_id(remote_url=None, local_path="/srv/repos/local-only")
    second = canonical_repository_id(
        remote_url=None, local_path="/tmp/other/local-only"
    )

    assert first != second
    assert first.startswith("repository:r_")


def test_repo_slug_from_remote_url_extracts_org_and_repo() -> None:
    remote_url = "git@github.com:PlatformContext/platform-context-graph.git"

    assert (
        repo_slug_from_remote_url(remote_url)
        == "platformcontext/platform-context-graph"
    )
