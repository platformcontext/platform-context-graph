"""Unit tests for api-node-boats e2e HTTP contract helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "api_node_boats_e2e_http_contract.py"


def _load_module():
    """Load the HTTP contract helper module from disk."""

    spec = importlib.util.spec_from_file_location(
        "api_node_boats_e2e_http_contract", _MODULE_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("api_node_boats_e2e_http_contract", None)
    sys.path.insert(0, str(_REPO_ROOT))
    sys.modules["api_node_boats_e2e_http_contract"] = module
    spec.loader.exec_module(module)
    return module


def test_resolve_repository_by_plain_name_uses_entities_resolve() -> None:
    """Name resolution should go through the public entity-resolution endpoint."""

    module = _load_module()

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "matches": [
                    {
                        "ref": {
                            "id": "repository:r_api-node-boats",
                            "name": "api-node-boats",
                            "type": "repository",
                        },
                        "score": 0.97,
                    }
                ]
            }

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> FakeResponse:
            assert path == "/entities/resolve"
            assert json == {
                "query": "api-node-boats",
                "types": ["repository"],
                "exact": True,
                "limit": 5,
            }
            return FakeResponse()

    repo_id = module.resolve_repository_id(FakeClient(), "api-node-boats")

    assert repo_id == "repository:r_api-node-boats"


def test_validate_bootstrap_contract_requires_story_and_context_fields() -> None:
    """Bootstrap validation should enforce the agreed blocking contract."""

    module = _load_module()
    story_payload = {"story": ["Public entrypoints: api-node-boats.qa.bgrp.io."]}
    context_payload = {
        "repository": {"name": "api-node-boats"},
        "api_surface": {"api_versions": ["v3"], "docs_routes": ["/_specs"]},
        "hostnames": [{"hostname": "api-node-boats.qa.bgrp.io"}],
        "provisioned_by": [{"name": "terraform-stack-node10"}],
        "platforms": [{"kind": "ecs", "name": "node10"}],
        "deploys_from": [{"name": "helm-charts"}],
        "environments": ["bg-qa"],
        "dependencies": [{"name": "api-node-forex"}],
    }

    module.validate_bootstrap_contract(
        story_payload=story_payload,
        context_payload=context_payload,
        subject_repository="api-node-boats",
        assertions={
            "blocking": [
                {"kind": "story_non_empty"},
                {"kind": "api_version", "value": "v3"},
                {"kind": "docs_route", "value": "/_specs"},
                {"kind": "hostname_contains", "value": "api-node-boats.qa"},
                {"kind": "provisioned_by", "value": "terraform-stack-node10"},
                {"kind": "platform_kind", "value": "ecs"},
                {"kind": "deploys_from", "value": "helm-charts"},
                {"kind": "environment_non_empty"},
                {"kind": "dependency", "value": "api-node-forex"},
            ]
        },
    )


def test_validate_scan_contract_requires_repo_reprocessing_and_story_delta() -> None:
    """Scan validation should require both reprocessing and downstream change."""

    module = _load_module()

    before = module.ScanSnapshot(
        repository_updated_at={
            "api-node-provisioning-indexer": "2026-03-31T01:00:00Z",
            "terraform-stack-node10": "2026-03-31T01:00:00Z",
        },
        story={"story": ["before"]},
        context={"deploys_from": [], "provisioned_by": []},
    )
    after = module.ScanSnapshot(
        repository_updated_at={
            "api-node-provisioning-indexer": "2026-03-31T02:00:00Z",
            "terraform-stack-node10": "2026-03-31T02:00:00Z",
        },
        story={"story": ["after"]},
        context={"deploys_from": [{"name": "helm-charts"}], "provisioned_by": []},
    )

    module.validate_scan_contract(
        before=before,
        after=after,
        assertions={
            "blocking": [
                {
                    "kind": "repo_reprocessed",
                    "repo": "api-node-provisioning-indexer",
                },
                {
                    "kind": "repo_reprocessed",
                    "repo": "terraform-stack-node10",
                },
                {"kind": "story_or_context_changed"},
            ]
        },
    )

    with pytest.raises(AssertionError, match="reprocessed"):
        module.validate_scan_contract(
            before=before,
            after=module.ScanSnapshot(
                repository_updated_at=before.repository_updated_at,
                story=after.story,
                context=after.context,
            ),
            assertions={
                "blocking": [
                    {
                        "kind": "repo_reprocessed",
                        "repo": "api-node-provisioning-indexer",
                    },
                    {"kind": "story_or_context_changed"},
                ]
            },
        )
