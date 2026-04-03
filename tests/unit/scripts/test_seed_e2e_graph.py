"""Unit tests for compose-backed e2e fixture-set selection."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "seed_e2e_graph.py"
_MODULE_SPEC = importlib.util.spec_from_file_location("seed_e2e_graph", _MODULE_PATH)
assert _MODULE_SPEC is not None
assert _MODULE_SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_MODULE_SPEC)
_MODULE_SPEC.loader.exec_module(_MODULE)

fixture_set_names = _MODULE.fixture_set_names
resolve_fixture_set = _MODULE.resolve_fixture_set


def test_fixture_set_names_lists_supported_corpora() -> None:
    """The seed script should advertise both supported fixture corpora."""

    assert fixture_set_names() == ("prompt_contract", "relationship_platform")


def test_resolve_fixture_set_defaults_to_prompt_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The seed script should keep the historical prompt-contract default."""

    monkeypatch.delenv("PCG_E2E_FIXTURE_SET", raising=False)

    fixtures_root, repositories = resolve_fixture_set()

    assert fixtures_root.name == "ecosystems"
    assert fixtures_root.parent.name == "fixtures"
    assert repositories[0] == "argocd_comprehensive"


def test_resolve_fixture_set_supports_relationship_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The new synthetic relationship-platform corpus should be selectable."""

    monkeypatch.setenv("PCG_E2E_FIXTURE_SET", "relationship_platform")

    fixtures_root, repositories = resolve_fixture_set()

    assert fixtures_root.name == "relationship_platform"
    assert fixtures_root.parent.name == "fixtures"
    assert "service-edge-api" in repositories
    assert "infra-runtime-modern" in repositories


def test_resolve_fixture_set_rejects_unknown_names() -> None:
    """Unknown fixture-set names should produce a helpful error."""

    with pytest.raises(ValueError, match="Unknown fixture set"):
        resolve_fixture_set("not-a-real-corpus")
