"""HTTP contract helpers for the local api-node-boats e2e harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ResponseProtocol(Protocol):
    """Minimal HTTP response surface used by the helpers."""

    def raise_for_status(self) -> None:
        """Raise when the response was unsuccessful."""

    def json(self) -> dict[str, Any]:
        """Return one decoded JSON payload."""


class ClientProtocol(Protocol):
    """Minimal HTTP client surface used by the helpers."""

    def post(self, path: str, json: dict[str, Any]) -> ResponseProtocol:
        """Send one POST request."""


@dataclass(frozen=True)
class ScanSnapshot:
    """Pre/post scan state used to validate downstream change."""

    repository_updated_at: dict[str, str]
    story: dict[str, Any]
    context: dict[str, Any]


def resolve_repository_id(client: ClientProtocol, repo_name: str) -> str:
    """Resolve one repository canonical id from the public entity API."""

    response = client.post(
        "/entities/resolve",
        json={
            "query": repo_name,
            "types": ["repository"],
            "exact": True,
            "limit": 5,
        },
    )
    response.raise_for_status()
    matches = list(response.json().get("matches") or [])
    if len(matches) != 1:
        raise AssertionError(
            f"Expected exactly one repository match for {repo_name}, got {len(matches)}"
        )
    resolved_id = str(matches[0].get("id") or "")
    if not resolved_id:
        raise AssertionError(f"No canonical repository id returned for {repo_name}")
    return resolved_id


def validate_bootstrap_contract(
    *,
    story_payload: dict[str, Any],
    context_payload: dict[str, Any],
    subject_repository: str,
) -> None:
    """Assert the agreed bootstrap truth-path contract."""

    assert list(story_payload.get("story") or []), "Repository story must be non-empty"
    assert context_payload["repository"]["name"] == subject_repository
    assert "v3" in list(context_payload["api_surface"]["api_versions"])
    assert "/_specs" in list(context_payload["api_surface"]["docs_routes"])
    assert list(context_payload.get("hostnames") or []), "Hostnames are required"
    assert any(
        str(row.get("name") or "") == "terraform-stack-node10"
        for row in list(context_payload.get("provisioned_by") or [])
    )
    assert any(
        str(row.get("kind") or "") == "ecs"
        for row in list(context_payload.get("platforms") or [])
    )
    assert any(
        str(row.get("name") or "") == "helm-charts"
        for row in list(context_payload.get("deploys_from") or [])
    )
    assert list(context_payload.get("environments") or []), "Environments are required"
    assert any(
        str(row.get("name") or "") == "api-node-forex"
        for row in list(context_payload.get("dependencies") or [])
    )


def validate_scan_contract(
    *,
    before: ScanSnapshot,
    after: ScanSnapshot,
    mutated_repositories: tuple[str, ...],
) -> None:
    """Assert both repo reprocessing and downstream api-node-boats change."""

    for repository_name in mutated_repositories:
        assert (
            before.repository_updated_at.get(repository_name)
            != after.repository_updated_at.get(repository_name)
        ), f"Mutated repository was not reprocessed: {repository_name}"

    assert (
        before.story != after.story or before.context != after.context
    ), "api-node-boats story or context must change after scan reprocessing"
