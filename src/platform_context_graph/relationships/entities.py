"""Canonical relationship entity primitives and identity helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from platform_context_graph.repository_identity import (
    canonical_repository_id,
    normalize_remote_url,
    repo_slug_from_remote_url,
)

__all__ = [
    "CanonicalEntity",
    "Platform",
    "PlatformEntity",
    "Repository",
    "RepositoryEntity",
    "WorkloadSubject",
    "WorkloadSubjectEntity",
    "canonical_platform_id",
    "canonical_workload_subject_id",
    "entity_from_id",
    "platform_from_entity_id",
    "workload_subject_from_entity_id",
]


def _normalize_token(value: str | None) -> str | None:
    """Return a lower-cased, trimmed token or ``None`` when empty."""

    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalize_path(value: str | None) -> str | None:
    """Return a stable repo-relative path representation."""

    if value is None:
        return None
    normalized = str(PurePosixPath(str(value).replace("\\", "/")).as_posix()).strip()
    normalized = normalized.strip("/")
    return normalized or None


@dataclass(slots=True, frozen=True)
class CanonicalEntity:
    """Shared fields for canonical relationship entities."""

    entity_id: str
    name: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class Repository(CanonicalEntity):
    """Canonical repository entity."""

    repo_slug: str | None = None
    remote_url: str | None = None
    local_path: str | None = None

    @classmethod
    def from_parts(
        cls,
        *,
        name: str,
        remote_url: str | None = None,
        local_path: str | Path | None = None,
        repo_slug: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> "Repository":
        """Build a canonical repository entity from portable repository metadata."""

        normalized_local_path = (
            str(Path(local_path).expanduser().resolve())
            if local_path is not None
            else None
        )
        normalized_remote_url = normalize_remote_url(remote_url)
        normalized_repo_slug = repo_slug or repo_slug_from_remote_url(
            normalized_remote_url
        )
        entity_id = canonical_repository_id(
            remote_url=normalized_remote_url,
            local_path=normalized_local_path,
        )
        return cls(
            entity_id=entity_id,
            name=name.strip(),
            repo_slug=normalized_repo_slug,
            remote_url=normalized_remote_url,
            local_path=normalized_local_path,
            details=details or {},
        )


def canonical_platform_id(
    *,
    kind: str,
    provider: str | None,
    name: str | None,
    environment: str | None,
    region: str | None,
    locator: str | None,
) -> str | None:
    """Build a canonical platform identifier or return ``None`` when unsafe."""

    normalized_kind = _normalize_token(kind)
    normalized_provider = _normalize_token(provider)
    normalized_name = _normalize_token(name)
    normalized_environment = _normalize_token(environment)
    normalized_region = _normalize_token(region)
    normalized_locator = _normalize_token(locator)

    discriminator = normalized_locator or normalized_name
    if discriminator is None and not (
        normalized_environment is not None and normalized_region is not None
    ):
        return None

    return (
        "platform:"
        f"{normalized_kind or 'none'}:"
        f"{normalized_provider or 'none'}:"
        f"{discriminator or 'none'}:"
        f"{normalized_environment or 'none'}:"
        f"{normalized_region or 'none'}"
    )


@dataclass(slots=True, frozen=True)
class Platform(CanonicalEntity):
    """Canonical runtime or orchestration platform entity."""

    kind: str = ""
    provider: str | None = None
    environment: str | None = None
    region: str | None = None
    locator: str | None = None

    @classmethod
    def from_parts(
        cls,
        *,
        kind: str,
        provider: str | None = None,
        name: str | None = None,
        environment: str | None = None,
        region: str | None = None,
        locator: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> "Platform":
        """Build a canonical platform entity from portable platform metadata."""

        entity_id = canonical_platform_id(
            kind=kind,
            provider=provider,
            name=name,
            environment=environment,
            region=region,
            locator=locator,
        )
        if entity_id is None:
            raise ValueError("platform metadata is not sufficiently specific")
        return cls(
            entity_id=entity_id,
            name=_normalize_token(name),
            details=details or {},
            kind=_normalize_token(kind) or "",
            provider=_normalize_token(provider),
            environment=_normalize_token(environment),
            region=_normalize_token(region),
            locator=locator.strip() if locator is not None and locator.strip() else None,
        )


def platform_from_entity_id(entity_id: str) -> Platform | None:
    """Parse one canonical platform id back into a lightweight entity."""

    if not entity_id.startswith("platform:"):
        return None
    try:
        rest = entity_id[len("platform:") :]
        kind, provider, remainder = rest.split(":", 2)
        discriminator, environment, region = remainder.rsplit(":", 2)
    except ValueError:
        return None
    normalized_discriminator = None if discriminator == "none" else discriminator
    display_name = _platform_display_name(normalized_discriminator)
    return Platform(
        entity_id=entity_id,
        name=display_name,
        details={},
        kind=kind if kind != "none" else "",
        provider=None if provider == "none" else provider,
        environment=None if environment == "none" else environment,
        region=None if region == "none" else region,
        locator=normalized_discriminator,
    )


def _platform_display_name(locator_or_name: str | None) -> str | None:
    """Return a human-readable platform name from a stored discriminator."""

    if locator_or_name is None:
        return None
    if "/" in locator_or_name:
        return locator_or_name.rsplit("/", 1)[-1] or locator_or_name
    if ":" in locator_or_name:
        return locator_or_name.rsplit(":", 1)[-1] or locator_or_name
    return locator_or_name


def canonical_workload_subject_id(
    *,
    repository_id: str | None,
    subject_type: str,
    name: str,
    environment: str | None,
    path: str | None,
) -> str:
    """Build a canonical workload-subject identifier."""

    normalized_repository_id = repository_id.strip() if repository_id is not None else None
    normalized_subject_type = _normalize_token(subject_type) or "none"
    normalized_name = _normalize_token(name) or "none"
    normalized_environment = _normalize_token(environment)
    normalized_path = _normalize_path(path)
    return (
        "workload-subject:"
        f"{normalized_repository_id or 'none'}:"
        f"{normalized_subject_type}:"
        f"{normalized_name}:"
        f"{normalized_environment or 'none'}:"
        f"{normalized_path or 'none'}"
    )


@dataclass(slots=True, frozen=True)
class WorkloadSubject(CanonicalEntity):
    """Canonical deployable workload subject entity."""

    repository_id: str | None = None
    subject_type: str = ""
    environment: str | None = None
    path: str | None = None

    @classmethod
    def from_parts(
        cls,
        *,
        repository_id: str | None,
        subject_type: str,
        name: str,
        environment: str | None = None,
        path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> "WorkloadSubject":
        """Build a canonical workload subject from portable deployment metadata."""

        entity_id = canonical_workload_subject_id(
            repository_id=repository_id,
            subject_type=subject_type,
            name=name,
            environment=environment,
            path=path,
        )
        return cls(
            entity_id=entity_id,
            name=_normalize_token(name),
            details=details or {},
            repository_id=repository_id.strip() if repository_id is not None else None,
            subject_type=_normalize_token(subject_type) or "",
            environment=_normalize_token(environment),
            path=_normalize_path(path),
        )


def workload_subject_from_entity_id(entity_id: str) -> WorkloadSubject | None:
    """Parse one canonical workload-subject id back into a lightweight entity."""

    if not entity_id.startswith("workload-subject:"):
        return None
    try:
        rest = entity_id[len("workload-subject:") :]
        repository_id, subject_type, name, environment, path = rest.rsplit(":", 4)
    except ValueError:
        return None
    return WorkloadSubject(
        entity_id=entity_id,
        name=None if name == "none" else name,
        details={},
        repository_id=None if repository_id == "none" else repository_id,
        subject_type="" if subject_type == "none" else subject_type,
        environment=None if environment == "none" else environment,
        path=None if path == "none" else path,
    )


def entity_from_id(entity_id: str) -> CanonicalEntity | None:
    """Return a canonical entity for one known entity id format."""

    if entity_id.startswith("repository:"):
        return Repository(entity_id=entity_id, name=entity_id)
    platform = platform_from_entity_id(entity_id)
    if platform is not None:
        return platform
    return workload_subject_from_entity_id(entity_id)


# Compatibility aliases kept for callers that still import the legacy *Entity names.
RepositoryEntity = Repository
PlatformEntity = Platform
WorkloadSubjectEntity = WorkloadSubject
