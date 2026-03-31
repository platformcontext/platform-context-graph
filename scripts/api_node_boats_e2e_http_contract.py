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


def _blocking_assertions(assertions: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized blocking assertion rows from the manifest payload."""

    rows = assertions.get("blocking") or []
    if not isinstance(rows, list):
        raise AssertionError("blocking assertions must be a list")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise AssertionError(f"blocking assertion must be a mapping: {row!r}")
        normalized.append(row)
    return normalized


def validate_bootstrap_contract(
    *,
    story_payload: dict[str, Any],
    context_payload: dict[str, Any],
    subject_repository: str,
    assertions: dict[str, Any],
) -> None:
    """Assert the agreed bootstrap truth-path contract."""

    assert context_payload["repository"]["name"] == subject_repository

    for assertion in _blocking_assertions(assertions):
        kind = str(assertion.get("kind") or "")
        if kind == "story_non_empty":
            assert list(story_payload.get("story") or []), "Repository story must be non-empty"
        elif kind == "api_version":
            expected_version = str(assertion.get("value") or "")
            assert expected_version in list(context_payload["api_surface"]["api_versions"])
        elif kind == "docs_route":
            expected_route = str(assertion.get("value") or "")
            assert expected_route in list(context_payload["api_surface"]["docs_routes"])
        elif kind == "hostname_contains":
            expected_fragment = str(assertion.get("value") or "")
            assert any(
                expected_fragment in str(row.get("hostname") or "")
                for row in list(context_payload.get("hostnames") or [])
            ), f"Expected hostname containing {expected_fragment}"
        elif kind == "provisioned_by":
            expected_name = str(assertion.get("value") or "")
            assert any(
                str(row.get("name") or "") == expected_name
                for row in list(context_payload.get("provisioned_by") or [])
            ), f"Expected provisioned_by repo {expected_name}"
        elif kind == "platform_kind":
            expected_kind = str(assertion.get("value") or "")
            assert any(
                str(row.get("kind") or "") == expected_kind
                for row in list(context_payload.get("platforms") or [])
            ), f"Expected platform kind {expected_kind}"
        elif kind == "deploys_from":
            expected_name = str(assertion.get("value") or "")
            assert any(
                str(row.get("name") or "") == expected_name
                for row in list(context_payload.get("deploys_from") or [])
            ), f"Expected deploys_from repo {expected_name}"
        elif kind == "environment_non_empty":
            assert list(context_payload.get("environments") or []), "Environments are required"
        elif kind == "dependency":
            expected_name = str(assertion.get("value") or "")
            assert any(
                str(row.get("name") or "") == expected_name
                for row in list(context_payload.get("dependencies") or [])
            ), f"Expected dependency repo {expected_name}"
        else:
            raise AssertionError(f"Unsupported bootstrap assertion kind: {kind}")


def validate_scan_contract(
    *,
    before: ScanSnapshot,
    after: ScanSnapshot,
    assertions: dict[str, Any],
) -> None:
    """Assert both repo reprocessing and downstream api-node-boats change."""

    for assertion in _blocking_assertions(assertions):
        kind = str(assertion.get("kind") or "")
        if kind == "repo_reprocessed":
            repository_name = str(assertion.get("repo") or "")
            assert (
                before.repository_updated_at.get(repository_name)
                != after.repository_updated_at.get(repository_name)
            ), f"Mutated repository was not reprocessed: {repository_name}"
        elif kind == "story_or_context_changed":
            assert (
                before.story != after.story or before.context != after.context
            ), "api-node-boats story or context must change after scan reprocessing"
        else:
            raise AssertionError(f"Unsupported scan assertion kind: {kind}")
