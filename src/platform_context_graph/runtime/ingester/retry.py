"""Retry classification and delay helpers for repository ingesters."""

from __future__ import annotations

import random
from datetime import datetime, timezone

import requests

DEFAULT_REPO_SYNC_RETRY_SECONDS = 5
MAX_REPO_SYNC_RETRY_SECONDS = 300


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


def _max_retry_exponent() -> int:
    """Return the exponent where exponential retry delay first hits the cap."""

    exponent = 0
    delay = DEFAULT_REPO_SYNC_RETRY_SECONDS
    while delay < MAX_REPO_SYNC_RETRY_SECONDS:
        delay *= 2
        exponent += 1
    return exponent


_MAX_RETRY_EXPONENT = _max_retry_exponent()


def classify_sync_error(exc: Exception) -> str:
    """Classify one repo-sync exception into a coarse runtime status kind."""

    if isinstance(
        exc,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ProxyError,
            requests.exceptions.SSLError,
        ),
    ):
        return "network"
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        if response is not None and response.status_code in {403, 429}:
            return "rate_limit"
        if response is not None and 500 <= response.status_code < 600:
            return "github_5xx"
        return "http"
    if isinstance(exc, ValueError):
        return "misconfigured"
    return "unknown"


def retry_after_seconds(exc: Exception, attempt: int) -> int:
    """Return bounded retry delay with jitter for transient sync failures."""

    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        retry_after = exc.response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(1, min(MAX_REPO_SYNC_RETRY_SECONDS, int(retry_after)))
            except ValueError:
                pass
        reset_header = exc.response.headers.get("X-RateLimit-Reset")
        if reset_header:
            try:
                reset_time = datetime.fromtimestamp(int(reset_header), tz=timezone.utc)
                wait_seconds = max(1, int((reset_time - _utc_now()).total_seconds()))
                return min(MAX_REPO_SYNC_RETRY_SECONDS, wait_seconds)
            except ValueError:
                pass
    exponent = min(_MAX_RETRY_EXPONENT, max(0, attempt - 1))
    base_delay = min(
        MAX_REPO_SYNC_RETRY_SECONDS,
        DEFAULT_REPO_SYNC_RETRY_SECONDS * (2**exponent),
    )
    jitter = random.randint(0, min(5, base_delay))
    return min(MAX_REPO_SYNC_RETRY_SECONDS, base_delay + jitter)
