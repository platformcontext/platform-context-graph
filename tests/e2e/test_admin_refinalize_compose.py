"""Compose-backed admin re-finalize smoke test."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

pytestmark = pytest.mark.e2e

_BASE_URL_ENV = "PCG_E2E_API_BASE_URL"
_API_KEY_ENV = "PCG_E2E_API_KEY"
_RUN_ID_FILE_ENV = "PCG_E2E_RUN_ID_FILE"
_STATUS_FILE_ENV = "PCG_E2E_STATUS_FILE"
_TIMEOUT_SECONDS_ENV = "PCG_E2E_TIMEOUT_SECONDS"


def _write_artifact(path_value: str | None, payload: str) -> None:
    """Persist one optional debugging artifact for the wrapper script."""

    if not path_value:
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _repository_id(repository: dict[str, object]) -> str | None:
    """Return the canonical repository id from a listing row."""

    value = repository.get("id") or repository.get("repo_id")
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    """Return an authenticated HTTP client for the live compose API."""

    base_url = os.getenv(_BASE_URL_ENV)
    api_key = os.getenv(_API_KEY_ENV)
    if not base_url or not api_key:
        pytest.skip(
            f"{_BASE_URL_ENV} and {_API_KEY_ENV} are required for compose e2e runs"
        )

    with httpx.Client(
        base_url=base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20.0,
    ) as live_client:
        yield live_client


def _get_json(client: httpx.Client, path: str) -> dict[str, object]:
    """Issue one GET request and return the decoded JSON payload."""

    response = client.get(path)
    response.raise_for_status()
    return response.json()


def _pick_repository_with_coverage(
    client: httpx.Client,
) -> tuple[str, dict[str, object]]:
    """Return the first repository that already exposes durable coverage."""

    repositories_payload = _get_json(client, "/repositories")
    repositories = list(repositories_payload.get("repositories") or [])
    assert repositories, "compose stack returned no repositories"

    for repository in repositories:
        repo_id = _repository_id(repository)
        if repo_id is None:
            continue
        coverage = _get_json(
            client,
            f"/repositories/{quote(repo_id, safe='')}/coverage",
        )
        if coverage.get("repo_id") == repo_id:
            return repo_id, coverage
    pytest.fail("unable to find a repository with durable coverage in compose")


def _pick_repository_story_with_runtime_signal(
    client: httpx.Client,
) -> tuple[str, dict[str, object]]:
    """Return one repository story that surfaces runtime or deployment evidence."""

    repositories_payload = _get_json(client, "/repositories")
    repositories = list(repositories_payload.get("repositories") or [])
    assert repositories, "compose stack returned no repositories"

    for repository in repositories:
        repo_id = _repository_id(repository)
        if repo_id is None:
            continue
        story = _get_json(client, f"/repositories/{quote(repo_id, safe='')}/story")
        deployment_overview = story.get("deployment_overview") or {}
        runtime_platforms = deployment_overview.get("runtime_platforms") or []
        deployment_story = story.get("story") or []
        if runtime_platforms or deployment_story:
            return repo_id, story
    pytest.fail("unable to find a repository story with runtime/deployment signal")


def _poll_refinalize_status(
    client: httpx.Client,
    *,
    run_id: str,
    timeout_seconds: int,
) -> dict[str, object]:
    """Poll admin status until the targeted run completes or times out."""

    deadline = time.monotonic() + timeout_seconds
    latest_status: dict[str, object] = {}
    while time.monotonic() < deadline:
        latest_status = _get_json(client, "/admin/refinalize/status")
        _write_artifact(
            os.getenv(_STATUS_FILE_ENV),
            json.dumps(latest_status, indent=2, sort_keys=True),
        )
        if latest_status.get("run_id") != run_id:
            time.sleep(1.0)
            continue
        if not latest_status.get("running", False):
            return latest_status
        time.sleep(2.0)
    pytest.fail(
        "admin refinalize did not finish before timeout; "
        f"last status was {json.dumps(latest_status, sort_keys=True)}"
    )


def test_admin_refinalize_compose_flow(client: httpx.Client) -> None:
    """Exercise admin re-finalize against the local compose stack."""

    repo_id, _coverage_before = _pick_repository_with_coverage(client)
    refinalize_response = client.post("/admin/refinalize", json={})
    refinalize_response.raise_for_status()
    started = refinalize_response.json()

    run_id = str(started.get("run_id") or "")
    assert run_id.startswith("refinalize-api-")
    _write_artifact(os.getenv(_RUN_ID_FILE_ENV), run_id)
    assert started.get("status") == "started"
    assert started.get("targeted_repo_count") == len(
        started.get("targeted_repo_ids") or []
    )

    status_payload = _poll_refinalize_status(
        client,
        run_id=run_id,
        timeout_seconds=int(os.getenv(_TIMEOUT_SECONDS_ENV, "180")),
    )
    assert status_payload.get("run_id") == run_id
    assert status_payload.get("last_error") in {None, ""}
    assert status_payload.get("current_stage") is None
    assert status_payload.get("stage_details") == {
        "run_id": run_id,
        "status": "completed",
    }
    timings = status_payload.get("last_timings") or {}
    assert "workloads" in timings
    assert "relationship_resolution" in timings

    coverage_after = _get_json(
        client,
        f"/repositories/{quote(repo_id, safe='')}/coverage",
    )
    assert coverage_after.get("repo_id") == repo_id
    assert coverage_after.get("finalization_status") == "completed"
    assert "finalization_incomplete" not in (coverage_after.get("limitations") or [])

    story_repo_id, story_payload = _pick_repository_story_with_runtime_signal(client)
    assert story_repo_id
    assert story_payload.get("deployment_overview") is not None
    assert story_payload.get("coverage") is not None
