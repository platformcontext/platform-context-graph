"""Compose-backed local api-node-boats bootstrap + scan verification."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

pytestmark = pytest.mark.e2e

_BASE_URL_ENV = "PCG_E2E_API_BASE_URL"
_API_KEY_ENV = "PCG_E2E_API_KEY"
_MANIFEST_ENV = "PCG_LOCAL_ECOSYSTEM_MANIFEST"
_WORKSPACE_INFO_ENV = "PCG_E2E_WORKSPACE_INFO"
_TIMEOUT_SECONDS_ENV = "PCG_E2E_TIMEOUT_SECONDS"


class _ResponseAdapter:
    """Small response wrapper with the methods our helpers expect."""

    def __init__(self, *, status_code: int, payload: dict[str, object]) -> None:
        self._status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        """Raise when the response was unsuccessful."""

        if self._status_code >= 400:
            raise RuntimeError(
                f"HTTP request failed with status {self._status_code}: {self._payload}"
            )

    def json(self) -> dict[str, object]:
        """Return the decoded JSON payload."""

        return self._payload


class _LiveApiClient:
    """Minimal base-URL-aware HTTP client for the compose e2e."""

    def __init__(self, *, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def close(self) -> None:
        """Close the underlying session."""

        return None

    def _request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> _ResponseAdapter:
        """Send one HTTP request and adapt the JSON response."""

        request = Request(
            url=f"{self._base_url}{path}",
            headers={
                **self._headers,
                "Content-Type": "application/json",
            },
            method=method,
            data=(
                None
                if payload is None
                else json.dumps(payload).encode("utf-8")
            ),
        )
        with urlopen(request, timeout=20.0) as response:
            body = response.read().decode("utf-8")
            decoded = json.loads(body) if body else {}
            return _ResponseAdapter(
                status_code=response.status,
                payload=decoded,
            )

    def get(self, path: str) -> _ResponseAdapter:
        """Send one authenticated GET request."""

        return self._request("GET", path)

    def post(
        self, path: str, json: dict[str, object] | None = None
    ) -> _ResponseAdapter:
        """Send one authenticated POST request."""

        return self._request("POST", path, payload=json)


@pytest.fixture(scope="module")
def client() -> _LiveApiClient:
    """Return an authenticated HTTP client for the live compose API."""

    base_url = os.getenv(_BASE_URL_ENV)
    api_key = os.getenv(_API_KEY_ENV)
    if not base_url or not api_key:
        pytest.skip(
            f"{_BASE_URL_ENV} and {_API_KEY_ENV} are required for compose e2e runs"
        )

    live_client = _LiveApiClient(base_url=base_url, api_key=api_key)
    try:
        yield live_client
    finally:
        live_client.close()


def _load_runtime_module(filename: str, module_name: str):
    """Load one scripts module from the current repository checkout."""

    import importlib.util
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


manifest_support = _load_runtime_module(
    "api_node_boats_e2e_manifest.py",
    "api_node_boats_e2e_manifest_e2e",
)
http_contract = _load_runtime_module(
    "api_node_boats_e2e_http_contract.py",
    "api_node_boats_e2e_http_contract_e2e",
)
mutations = _load_runtime_module(
    "api_node_boats_e2e_mutations.py",
    "api_node_boats_e2e_mutations_e2e",
)


def _get_json(client: _LiveApiClient, path: str) -> dict[str, object]:
    """Return one decoded JSON payload."""

    response = client.get(path)
    response.raise_for_status()
    return response.json()


def _repository_story(client: _LiveApiClient, repo_id: str) -> dict[str, object]:
    """Return one repository story payload."""

    return _get_json(client, f"/repositories/{quote(repo_id, safe='')}/story")


def _repository_context(client: _LiveApiClient, repo_id: str) -> dict[str, object]:
    """Return one repository context payload."""

    return _get_json(client, f"/repositories/{quote(repo_id, safe='')}/context")


def _repository_coverage(client: _LiveApiClient, repo_id: str) -> dict[str, object]:
    """Return one repository coverage payload."""

    return _get_json(client, f"/repositories/{quote(repo_id, safe='')}/coverage")


def _load_workspace_info() -> dict[str, object]:
    """Return the prepared disposable workspace info artifact."""

    path_value = os.getenv(_WORKSPACE_INFO_ENV)
    if not path_value:
        pytest.skip(f"{_WORKSPACE_INFO_ENV} is required for this compose e2e")
    return json.loads(Path(path_value).read_text(encoding="utf-8"))


def _poll_scan_completion(
    client: _LiveApiClient,
    *,
    request_token: str,
    timeout_seconds: int,
) -> dict[str, object]:
    """Poll ingester status until the requested scan completes."""

    deadline = time.monotonic() + timeout_seconds
    latest_status: dict[str, object] = {}
    while time.monotonic() < deadline:
        latest_status = _get_json(client, "/ingesters/repository")
        if (
            latest_status.get("scan_request_token") == request_token
            and latest_status.get("scan_request_state") in {"running", "completed"}
        ):
            if (
                latest_status.get("scan_request_state") == "completed"
                and latest_status.get("status") == "idle"
            ):
                return latest_status
        elif (
            latest_status.get("scan_request_state") == "completed"
            and latest_status.get("status") == "idle"
        ):
            pytest.fail(
                "repository scan completed under a different request token: "
                f"expected {request_token}, got {latest_status.get('scan_request_token')}"
            )
        time.sleep(2.0)
    pytest.fail(f"repository scan did not complete before timeout: {latest_status}")


def test_api_node_boats_reindex_compose_flow(client: _LiveApiClient) -> None:
    """Exercise bootstrap validation, evidence mutation, and scan reindex."""

    manifest_path = os.getenv(_MANIFEST_ENV)
    if not manifest_path:
        pytest.skip(f"{_MANIFEST_ENV} is required for this compose e2e")
    manifest = manifest_support.load_manifest(manifest_path)
    workspace_info = _load_workspace_info()
    working_copies = {
        name: Path(path_value)
        for name, path_value in dict(workspace_info["working_copies"]).items()
    }

    subject_repo_id = http_contract.resolve_repository_id(
        client, manifest.subject_repository
    )
    bootstrap_story = _repository_story(client, subject_repo_id)
    bootstrap_context = _repository_context(client, subject_repo_id)
    http_contract.validate_bootstrap_contract(
        story_payload=bootstrap_story,
        context_payload=bootstrap_context,
        subject_repository=manifest.subject_repository,
        assertions=manifest.bootstrap_assertions,
    )

    mutation_repo_ids: dict[str, str] = {}
    mutation_updated_at: dict[str, str] = {}
    for mutation in manifest.scan_mutations:
        repository_name = str(mutation.get("repo") or "")
        if not repository_name:
            pytest.fail("scan_mutations entries must include 'repo'")
        repo_id = http_contract.resolve_repository_id(client, repository_name)
        mutation_repo_ids[repository_name] = repo_id
        mutation_updated_at[repository_name] = str(
            _repository_coverage(client, repo_id).get("updated_at") or ""
        )
        target_path = working_copies[repository_name] / str(mutation.get("file") or "")
        if repository_name == "api-node-provisioning-indexer":
            mutations.apply_workflow_mutation(target_path)
        elif repository_name == "terraform-stack-node10":
            mutations.apply_terraform_mutation(target_path)
        else:
            pytest.fail(f"Unsupported mutation repository: {repository_name}")

    scan_response = client.post("/ingesters/repository/scan")
    scan_response.raise_for_status()
    accepted = scan_response.json()
    assert accepted.get("accepted") is True
    request_token = str(accepted.get("scan_request_token") or "")
    assert request_token, "scan request token must be present"

    _poll_scan_completion(
        client,
        request_token=request_token,
        timeout_seconds=int(os.getenv(_TIMEOUT_SECONDS_ENV, "300")),
    )

    after_story = _repository_story(client, subject_repo_id)
    after_context = _repository_context(client, subject_repo_id)
    http_contract.validate_bootstrap_contract(
        story_payload=after_story,
        context_payload=after_context,
        subject_repository=manifest.subject_repository,
        assertions=manifest.bootstrap_assertions,
    )
    after_updated_at = {
        repository_name: str(
            _repository_coverage(client, repo_id).get("updated_at") or ""
        )
        for repository_name, repo_id in mutation_repo_ids.items()
    }
    http_contract.validate_scan_contract(
        before=http_contract.ScanSnapshot(
            repository_updated_at=mutation_updated_at,
            story=bootstrap_story,
            context=bootstrap_context,
        ),
        after=http_contract.ScanSnapshot(
            repository_updated_at=after_updated_at,
            story=after_story,
            context=after_context,
        ),
        assertions=manifest.scan_assertions,
    )
