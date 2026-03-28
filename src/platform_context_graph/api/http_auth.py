"""HTTP bearer-auth helpers for the FastAPI and HTTP MCP surfaces."""

from __future__ import annotations

import hmac
import os
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from ..paths import get_app_env_file

__all__ = [
    "PUBLIC_HTTP_PATHS",
    "ensure_http_api_key",
    "http_auth_enabled",
    "http_auth_middleware",
    "is_public_http_path",
]

_FALSEY = {"0", "false", "no", "off"}
PUBLIC_HTTP_PATHS = {
    "/health",
    "/api/v0/health",
    "/api/v0/openapi.json",
    "/api/v0/docs",
    "/api/v0/redoc",
}


def _configured_http_api_key() -> str | None:
    """Return the configured HTTP bearer token when present."""

    raw = os.getenv("PCG_API_KEY")
    if raw is None:
        return None
    token = raw.strip()
    return token or None


def http_auth_enabled() -> bool:
    """Report whether HTTP bearer auth is active for this process."""

    return _configured_http_api_key() is not None


def is_public_http_path(path: str) -> bool:
    """Return whether a request path is intentionally public."""

    return path in PUBLIC_HTTP_PATHS


def _should_auto_generate_http_api_key() -> bool:
    """Return whether local bootstrap may generate a new bearer token."""

    raw = os.getenv("PCG_AUTO_GENERATE_API_KEY")
    if raw is None:
        return False
    return raw.strip().lower() not in _FALSEY


def _persist_env_value(path: Path, *, key: str, value: str) -> None:
    """Write or replace one environment variable in a dotenv-style file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    updated_lines: list[str] = []
    replaced = False
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            current_key = stripped.split("=", 1)[0].strip()
            if current_key == key:
                updated_lines.append(f"{key}={value}")
                replaced = True
                continue
        updated_lines.append(line)

    if not replaced:
        if updated_lines and updated_lines[-1] != "":
            updated_lines.append("")
        updated_lines.append(f"{key}={value}")

    path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def ensure_http_api_key() -> str:
    """Return the configured HTTP API key, generating one when explicitly allowed.

    Raises:
        ValueError: If the process owns a networked HTTP surface but no bearer
            token is configured and auto-generation is not enabled.
    """

    token = _configured_http_api_key()
    if token is not None:
        return token

    if not _should_auto_generate_http_api_key():
        raise ValueError(
            "PCG_API_KEY is required for networked HTTP API/MCP startup. "
            "Set PCG_API_KEY or enable PCG_AUTO_GENERATE_API_KEY for explicit "
            "local bootstrap flows."
        )

    token = secrets.token_urlsafe(32)
    _persist_env_value(get_app_env_file(), key="PCG_API_KEY", value=token)
    os.environ["PCG_API_KEY"] = token
    return token


def _unauthorized_response() -> JSONResponse:
    """Return the standard bearer-auth rejection response."""

    return JSONResponse(
        status_code=401,
        content={"detail": "Unauthorized"},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def http_auth_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Protect non-public HTTP routes when a bearer token is configured."""

    expected_token = _configured_http_api_key()
    if expected_token is None or is_public_http_path(request.url.path):
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        return _unauthorized_response()

    if not hmac.compare_digest(credentials.strip(), expected_token):
        return _unauthorized_response()

    return await call_next(request)
