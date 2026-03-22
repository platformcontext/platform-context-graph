"""GitHub App authentication and GitHub API retry helpers."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import jwt
import requests

from platform_context_graph.utils.debug_log import warning_logger

DEFAULT_GITHUB_API_RETRY_ATTEMPTS = 5
DEFAULT_GITHUB_API_RETRY_DELAY_SECONDS = 5.0
DEFAULT_GITHUB_APP_TOKEN_REFRESH_SECONDS = 60
_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class CachedGitHubAppToken:
    """Cached GitHub App installation token with expiry metadata."""

    token: str
    expires_at: datetime | None


_CACHED_GITHUB_APP_TOKEN: CachedGitHubAppToken | None = None


def _github_api_retry_attempts() -> int:
    """Return the number of attempts for transient GitHub API failures."""

    return max(
        1,
        int(
            os.getenv(
                "PCG_GITHUB_API_RETRY_ATTEMPTS",
                str(DEFAULT_GITHUB_API_RETRY_ATTEMPTS),
            )
        ),
    )


def _github_api_retry_delay_seconds() -> float:
    """Return the delay between GitHub API retry attempts."""

    return max(
        0.0,
        float(
            os.getenv(
                "PCG_GITHUB_API_RETRY_DELAY_SECONDS",
                str(DEFAULT_GITHUB_API_RETRY_DELAY_SECONDS),
            )
        ),
    )


def _token_refresh_window_seconds() -> int:
    """Return the safety window before token expiry that triggers refresh."""

    return max(
        1,
        int(
            os.getenv(
                "PCG_GITHUB_APP_TOKEN_REFRESH_SECONDS",
                str(DEFAULT_GITHUB_APP_TOKEN_REFRESH_SECONDS),
            )
        ),
    )


def clear_cached_github_app_token() -> None:
    """Clear the cached GitHub App installation token."""

    global _CACHED_GITHUB_APP_TOKEN
    with _CACHE_LOCK:
        _CACHED_GITHUB_APP_TOKEN = None


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp into a timezone-aware datetime."""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_retry_after_seconds(response: requests.Response) -> float:
    """Return the retry delay advertised by a rate-limited response."""

    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_after_time = parsedate_to_datetime(retry_after)
            except (TypeError, ValueError, IndexError):
                retry_after_time = None
            if retry_after_time is not None:
                if retry_after_time.tzinfo is None:
                    retry_after_time = retry_after_time.replace(tzinfo=timezone.utc)
                return max(
                    0.0, (retry_after_time - datetime.now(timezone.utc)).total_seconds()
                )

    reset_after = response.headers.get("X-RateLimit-Reset")
    if reset_after:
        try:
            reset_at = datetime.fromtimestamp(float(reset_after), tz=timezone.utc)
            return max(
                0.0, (reset_at - datetime.now(timezone.utc)).total_seconds()
            )
        except ValueError:
            return _github_api_retry_delay_seconds()

    return _github_api_retry_delay_seconds()


def _is_rate_limited_response(response: requests.Response) -> bool:
    """Return whether a response indicates GitHub rate limiting."""

    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False

    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining == "0":
        return True

    retry_after = response.headers.get("Retry-After")
    if retry_after:
        return True

    body = ""
    try:
        body = str(response.text or "")
    except Exception:
        body = ""
    return "rate limit" in body.lower()


def _is_retriable_github_error(exc: requests.RequestException) -> bool:
    """Return whether a GitHub API error should be retried."""

    response = getattr(exc, "response", None)
    if response is None:
        return True
    return int(response.status_code) >= 500


def github_api_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Execute a GitHub API request with retries for transient failures.

    Args:
        method: HTTP method name.
        url: GitHub API URL.
        **kwargs: Keyword arguments forwarded to ``requests.request``.

    Returns:
        The successful GitHub response.
    """

    attempts = _github_api_retry_attempts()
    delay_seconds = _github_api_retry_delay_seconds()
    last_error: requests.RequestException | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = requests.request(method, url, **kwargs)
            if _is_rate_limited_response(response):
                retry_seconds = _parse_retry_after_seconds(response)
                warning_logger(
                    f"GitHub API rate limit hit on attempt {attempt}/{attempts}: "
                    f"status={response.status_code} retry_after={retry_seconds:.0f}s url={url}"
                )
                if attempt >= attempts:
                    response.raise_for_status()
                if retry_seconds > 0:
                    time.sleep(retry_seconds)
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= attempts or not _is_retriable_github_error(exc):
                raise
            warning_logger(
                f"GitHub API request failed on attempt {attempt}/{attempts}: {exc}"
            )
            if delay_seconds > 0:
                time.sleep(delay_seconds)

    assert last_error is not None
    raise last_error


def _installation_token_expired_or_stale(
    cached: CachedGitHubAppToken | None,
) -> bool:
    """Return whether the cached installation token needs a refresh."""

    if cached is None or cached.expires_at is None:
        return True

    refresh_window_seconds = _token_refresh_window_seconds()
    return (
        cached.expires_at - datetime.now(timezone.utc)
    ).total_seconds() <= refresh_window_seconds


def _mint_github_app_token() -> CachedGitHubAppToken:
    """Mint a GitHub App installation token and capture its expiry."""

    app_id = require_env("GITHUB_APP_ID")
    installation_id = require_env("GITHUB_APP_INSTALLATION_ID")
    private_key = require_env("GITHUB_APP_PRIVATE_KEY")
    now = int(time.time())
    encoded = jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": app_id},
        private_key,
        algorithm="RS256",
    )
    response = github_api_request(
        "post",
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers=github_headers(encoded),
        timeout=15,
    )
    payload = response.json()
    token = payload.get("token")
    if not token:
        raise RuntimeError("GitHub App token response did not include a token")
    return CachedGitHubAppToken(
        token=str(token),
        expires_at=_parse_datetime(str(payload.get("expires_at") or "")),
    )


def github_app_token() -> str:
    """Mint or reuse a GitHub App installation token from environment credentials."""

    global _CACHED_GITHUB_APP_TOKEN
    with _CACHE_LOCK:
        if not _installation_token_expired_or_stale(_CACHED_GITHUB_APP_TOKEN):
            assert _CACHED_GITHUB_APP_TOKEN is not None
            return _CACHED_GITHUB_APP_TOKEN.token

        cached = _mint_github_app_token()
        _CACHED_GITHUB_APP_TOKEN = cached
        return cached.token


def github_headers(token: str) -> dict[str, str]:
    """Build GitHub API headers for the supplied token."""

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def require_env(name: str) -> str:
    """Return a required environment variable or raise a configuration error."""

    value = os.getenv(name)
    if not value:
        raise ValueError(f"Required environment variable {name} is not set")
    return value
