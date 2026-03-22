"""Repository identity helpers for remote-first repository references."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

__all__ = [
    "build_repo_access",
    "canonical_repository_id",
    "git_remote_for_path",
    "normalize_remote_url",
    "relative_path_from_local",
    "repo_slug_from_remote_url",
    "repository_metadata",
]


def normalize_remote_url(remote_url: str | None) -> str | None:
    """Normalize SSH and HTTPS git remotes into one canonical HTTPS form.

    Args:
        remote_url: Raw git remote URL as discovered from configuration or git.

    Returns:
        A normalized HTTPS-style remote URL, or ``None`` when the input is empty
        or cannot be reduced to a meaningful repository location.
    """
    if remote_url is None:
        return None

    candidate = remote_url.strip()
    if not candidate:
        return None

    host: str | None = None
    path: str | None = None

    if candidate.startswith("git@") and ":" in candidate:
        _, _, remainder = candidate.partition("@")
        host, _, path = remainder.partition(":")
    elif candidate.startswith("ssh://"):
        parsed = urlsplit(candidate)
        host = parsed.hostname
        path = parsed.path
    elif "://" in candidate:
        parsed = urlsplit(candidate)
        host = parsed.hostname
        path = parsed.path

    if host is None or path is None:
        return candidate.rstrip("/")

    clean_path = path.lstrip("/").rstrip("/")
    if clean_path.endswith(".git"):
        clean_path = clean_path[:-4]
    clean_path = "/".join(part for part in clean_path.split("/") if part)
    if not clean_path:
        return None

    return f"https://{host.lower()}/{clean_path.lower()}"


def repo_slug_from_remote_url(remote_url: str | None) -> str | None:
    """Return the ``org/repo`` slug derived from a remote URL.

    Args:
        remote_url: Raw or normalized remote URL.

    Returns:
        The repository slug portion of the remote URL, or ``None`` when the URL
        cannot be normalized into a slug.
    """
    normalized = normalize_remote_url(remote_url)
    if normalized is None:
        return None

    parsed = urlsplit(normalized)
    clean_path = parsed.path.lstrip("/").rstrip("/")
    return clean_path or None


def canonical_repository_id(*, remote_url: str | None, local_path: str | None) -> str:
    """Build the canonical repository identifier for API and graph usage.

    Args:
        remote_url: Remote URL used as the primary stable identity when present.
        local_path: Local checkout path used only as a fallback identity source
            when no remote is available.

    Returns:
        Canonical repository identifier with the ``repository:`` prefix.

    Raises:
        ValueError: If neither a remote URL nor a local path is available.
    """
    identity = normalize_remote_url(remote_url)
    if identity is None:
        if local_path is None:
            raise ValueError("local_path is required when remote_url is not available")
        identity = str(Path(local_path).expanduser().resolve())
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:8]
    return f"repository:r_{digest}"


def git_remote_for_path(path: str | Path) -> str | None:
    """Read the ``origin`` remote URL for a checkout path.

    Args:
        path: Repository checkout directory.

    Returns:
        The configured ``origin`` remote URL, or ``None`` when the directory is
        not a git repository or has no configured origin.
    """
    repo_path = Path(path).expanduser().resolve()
    result = subprocess.run(
        ["git", "-C", str(repo_path), "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    remote_url = result.stdout.strip()
    return remote_url or None


def repository_metadata(
    *,
    name: str,
    local_path: str | Path | None,
    remote_url: str | None = None,
    repo_slug: str | None = None,
    has_remote: bool | None = None,
) -> dict[str, Any]:
    """Build normalized repository metadata for storage and API responses.

    Args:
        name: Human-readable repository name.
        local_path: Local checkout path when known.
        remote_url: Remote URL discovered from git or sync configuration.
        repo_slug: Optional explicit repository slug.
        has_remote: Optional explicit remote-presence flag.

    Returns:
        Normalized repository metadata with canonical ID, remote-first identity,
        and explicit local checkout metadata.
    """
    normalized_local_path = (
        str(Path(local_path).expanduser().resolve()) if local_path is not None else None
    )
    normalized_remote_url = normalize_remote_url(remote_url)
    normalized_repo_slug = repo_slug or repo_slug_from_remote_url(normalized_remote_url)
    remote_present = (
        has_remote if has_remote is not None else normalized_remote_url is not None
    )

    return {
        "id": canonical_repository_id(
            remote_url=normalized_remote_url,
            local_path=normalized_local_path,
        ),
        "name": name,
        "repo_slug": normalized_repo_slug,
        "remote_url": normalized_remote_url,
        "local_path": normalized_local_path,
        "has_remote": bool(remote_present),
    }


def build_repo_access(
    repository: Mapping[str, Any],
    *,
    interaction_mode: str = "conversational",
) -> dict[str, Any]:
    """Build the local-access handoff contract for remote PCG deployments.

    Args:
        repository: Normalized repository metadata containing canonical identity
            and optional local checkout information.
        interaction_mode: How the client should ask the user for follow-up
            access details.

    Returns:
        Structured repository-access metadata for MCP or HTTP responses.

    Raises:
        ValueError: If the repository mapping does not include a canonical ID.
    """
    repo_id = repository.get("id")
    if repo_id is None:
        raise ValueError("repository metadata must include an id")

    repo_slug = repository.get("repo_slug")
    remote_url = repository.get("remote_url")
    local_path = repository.get("local_path")

    if local_path:
        state = "needs_local_checkout"
        recommended_action = "ask_user_for_local_path"
    else:
        state = "unknown"
        recommended_action = (
            "clone_locally" if remote_url else "ask_user_for_local_path"
        )

    return {
        "state": state,
        "repo_id": repo_id,
        "repo_slug": repo_slug,
        "remote_url": remote_url,
        "local_path": local_path,
        "recommended_action": recommended_action,
        "interaction_mode": interaction_mode,
    }


def relative_path_from_local(
    path: str | Path | None, local_path: str | Path | None
) -> str | None:
    """Return a repo-relative path when the file lives under the repo root.

    Args:
        path: Candidate file path.
        local_path: Local repository root used to relativize the file.

    Returns:
        Repo-relative POSIX path when the file is under ``local_path``.
        Otherwise returns the normalized original path, or ``None`` when the
        file path is missing.
    """
    if path is None:
        return None
    file_path = Path(path)
    if not file_path.is_absolute():
        return file_path.as_posix()
    if local_path is None:
        return file_path.as_posix()

    repo_root = Path(local_path)
    try:
        return file_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return file_path.as_posix()
