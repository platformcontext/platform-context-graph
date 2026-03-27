from __future__ import annotations

import importlib
import os

import pytest


def test_ensure_http_api_key_returns_existing_env_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    auth = importlib.import_module("platform_context_graph.api.http_auth")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PCG_HOME", str(tmp_path))
    monkeypatch.setenv("PCG_API_KEY", "existing-key")
    monkeypatch.delenv("PCG_AUTO_GENERATE_API_KEY", raising=False)

    assert auth.ensure_http_api_key() == "existing-key"
    assert not (tmp_path / ".env").exists()


def test_ensure_http_api_key_generates_and_persists_for_local_bootstrap(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    auth = importlib.import_module("platform_context_graph.api.http_auth")
    cli_main = importlib.import_module("platform_context_graph.cli.main")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PCG_HOME", str(tmp_path))
    monkeypatch.delenv("PCG_API_KEY", raising=False)
    monkeypatch.setenv("PCG_AUTO_GENERATE_API_KEY", "true")

    token = auth.ensure_http_api_key()

    env_file = tmp_path / ".env"
    assert token
    assert env_file.exists()
    assert f"PCG_API_KEY={token}" in env_file.read_text(encoding="utf-8")

    monkeypatch.delenv("PCG_API_KEY", raising=False)
    cli_main._load_credentials()

    assert os.environ["PCG_API_KEY"] == token


def test_ensure_http_api_key_requires_explicit_token_when_autogeneration_is_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    auth = importlib.import_module("platform_context_graph.api.http_auth")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PCG_HOME", str(tmp_path))
    monkeypatch.delenv("PCG_API_KEY", raising=False)
    monkeypatch.delenv("PCG_AUTO_GENERATE_API_KEY", raising=False)

    with pytest.raises(ValueError, match="PCG_API_KEY"):
        auth.ensure_http_api_key()
