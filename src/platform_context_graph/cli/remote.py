"""Shared helpers for explicit remote-aware CLI command execution."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import requests
import typer

from . import config_manager

_DEFAULT_REMOTE_TIMEOUT_SECONDS = 60


class RemoteAPIError(RuntimeError):
    """Raised when a remote HTTP API request fails."""


@dataclass(frozen=True)
class RemoteTarget:
    """Resolved remote API target and auth configuration."""

    service_url: str
    api_key: str | None
    profile: str | None
    timeout_seconds: int

    @property
    def headers(self) -> dict[str, str]:
        """Return base HTTP headers for remote API requests."""

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


def remote_mode_requested(
    service_url: str | None = None,
    profile: str | None = None,
) -> bool:
    """Return whether one command explicitly requested remote mode."""

    return bool(
        (service_url is not None and service_url.strip())
        or (profile is not None and profile.strip())
    )


def _normalized_profile_suffix(profile: str | None) -> str | None:
    """Normalize a profile name into an uppercase config key suffix."""

    if profile is None or not profile.strip():
        return None
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", profile.strip().upper()).strip("_")
    return normalized or None


def _lookup_config_value(config: dict[str, str], key: str | None) -> str | None:
    """Return one config value from environment or loaded config mappings."""

    if key is None:
        return None
    environment_value = os.getenv(key)
    if environment_value and environment_value.strip():
        return environment_value.strip()
    configured_value = config.get(key)
    if configured_value and str(configured_value).strip():
        return str(configured_value).strip()
    return None


def _parse_timeout_seconds(raw_value: str | int | None) -> int:
    """Normalize one remote timeout value with a safe fallback."""

    if raw_value is None:
        return _DEFAULT_REMOTE_TIMEOUT_SECONDS
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return _DEFAULT_REMOTE_TIMEOUT_SECONDS


def resolve_remote_target(
    *,
    service_url: str | None = None,
    api_key: str | None = None,
    profile: str | None = None,
    timeout_seconds: int | None = None,
    require_remote: bool = False,
) -> RemoteTarget | None:
    """Resolve the explicit remote target for one CLI command."""

    if not remote_mode_requested(service_url, profile):
        if not require_remote:
            return None
    config = config_manager.load_config()
    resolved_profile = profile
    if resolved_profile is None and (
        remote_mode_requested(service_url, profile) or require_remote
    ):
        resolved_profile = _lookup_config_value(config, "PCG_SERVICE_PROFILE")
    profile_suffix = _normalized_profile_suffix(resolved_profile)

    resolved_service_url = (
        service_url.strip() if service_url and service_url.strip() else None
    )
    if resolved_service_url is None:
        resolved_service_url = _lookup_config_value(
            config,
            f"PCG_SERVICE_URL_{profile_suffix}" if profile_suffix else None,
        ) or _lookup_config_value(config, "PCG_SERVICE_URL")
    if resolved_service_url is None:
        raise typer.BadParameter(
            "Remote mode requires --service-url or a configured PCG_SERVICE_URL."
        )

    resolved_api_key = api_key.strip() if api_key and api_key.strip() else None
    if resolved_api_key is None:
        resolved_api_key = _lookup_config_value(
            config,
            f"PCG_API_KEY_{profile_suffix}" if profile_suffix else None,
        ) or _lookup_config_value(config, "PCG_API_KEY")

    resolved_timeout_seconds = (
        timeout_seconds
        if timeout_seconds is not None
        else _parse_timeout_seconds(
            _lookup_config_value(config, "PCG_REMOTE_TIMEOUT_SECONDS")
        )
    )
    return RemoteTarget(
        service_url=resolved_service_url.rstrip("/"),
        api_key=resolved_api_key,
        profile=resolved_profile,
        timeout_seconds=max(1, int(resolved_timeout_seconds)),
    )


def request_json(
    target: RemoteTarget,
    *,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    timeout_seconds: int | None = None,
) -> Any:
    """Issue one HTTP request to the remote API and decode JSON."""

    url = f"{target.service_url}/{path.lstrip('/')}"
    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=target.headers,
            params=params,
            json=json_body,
            files=files,
            data=data,
            timeout=timeout_seconds or target.timeout_seconds,
        )
    except requests.RequestException as exc:
        raise RemoteAPIError(str(exc)) from exc

    if response.status_code >= 400:
        message = response.text
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            message = str(
                payload.get("detail") or payload.get("message") or response.text
            )
        raise RemoteAPIError(message)

    try:
        return response.json()
    except ValueError as exc:
        raise RemoteAPIError(f"Remote service returned invalid JSON: {exc}") from exc


def print_json_payload(console: Any, payload: Any) -> None:
    """Pretty-print one JSON payload to the CLI console."""

    console.print_json(data=payload, default=str)
