"""Configuration models for repo synchronization runtimes."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class RepoSyncRepositoryRule:
    """Include rule for selecting repositories to sync.

    Attributes:
        kind: Match type, either ``exact`` or ``regex``.
        value: Exact repository identifier or regular-expression pattern.
    """

    kind: str
    value: str

    def matches(self, repository_id: str) -> bool:
        """Return whether the repository identifier matches the rule.

        Args:
            repository_id: Repository identifier, typically ``org/repo``.

        Returns:
            ``True`` when the repository matches the rule.
        """

        if self.kind == "exact":
            return repository_id == self.value
        if self.kind == "regex":
            return re.fullmatch(self.value, repository_id) is not None
        raise ValueError(f"Unsupported repository rule kind: {self.kind}")


def _normalize_rule_kind(value: Any) -> str:
    """Normalize a repository rule kind value.

    Args:
        value: Raw rule kind value.

    Returns:
        Normalized rule kind.
    """

    normalized = str(value).strip().lower()
    if normalized in {"exact", "regex"}:
        return normalized
    raise ValueError(f"Unsupported repository rule kind: {value!r}")


def _repository_rule_from_mapping(mapping: Mapping[str, Any]) -> RepoSyncRepositoryRule:
    """Convert a JSON rule mapping into a repository include rule.

    Args:
        mapping: Parsed rule mapping from JSON.

    Returns:
        Normalized repository include rule.
    """

    if "type" in mapping or "kind" in mapping or "match" in mapping:
        kind = mapping.get("type", mapping.get("kind", mapping.get("match")))
        value = mapping.get("value", mapping.get("pattern"))
        if value is None:
            raise ValueError(f"Repository rule is missing a value: {mapping!r}")
        return RepoSyncRepositoryRule(kind=_normalize_rule_kind(kind), value=str(value))

    if "exact" in mapping and len(mapping) == 1:
        return RepoSyncRepositoryRule(kind="exact", value=str(mapping["exact"]))
    if "regex" in mapping and len(mapping) == 1:
        return RepoSyncRepositoryRule(kind="regex", value=str(mapping["regex"]))

    raise ValueError(f"Unsupported repository rule mapping: {mapping!r}")


def parse_repository_rules_json(raw: str | None) -> tuple[RepoSyncRepositoryRule, ...]:
    """Parse structured repository include rules from JSON.

    Args:
        raw: JSON payload from ``PCG_REPOSITORY_RULES_JSON``.

    Returns:
        Parsed repository include rules.
    """

    if raw is None or not raw.strip():
        return ()

    parsed = json.loads(raw)
    rules: list[RepoSyncRepositoryRule] = []
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, str):
                rules.append(RepoSyncRepositoryRule(kind="exact", value=item))
            elif isinstance(item, Mapping):
                rules.append(_repository_rule_from_mapping(item))
            else:
                raise ValueError(f"Unsupported repository rule entry: {item!r}")
        return tuple(rules)

    if isinstance(parsed, Mapping):
        exact_values = parsed.get("exact", ())
        regex_values = parsed.get("regex", ())
        if isinstance(exact_values, str):
            exact_values = (exact_values,)
        if isinstance(regex_values, str):
            regex_values = (regex_values,)
        rules.extend(
            RepoSyncRepositoryRule(kind="exact", value=str(value))
            for value in exact_values
        )
        rules.extend(
            RepoSyncRepositoryRule(kind="regex", value=str(value))
            for value in regex_values
        )
        if rules:
            return tuple(rules)

    raise ValueError(
        "PCG_REPOSITORY_RULES_JSON must be a JSON list of rules or an object with "
        "exact/regex keys"
    )


def extract_exact_repository_ids(
    rules: Sequence[RepoSyncRepositoryRule],
) -> list[str]:
    """Return de-duplicated exact repository identifiers from structured rules.

    Args:
        rules: Structured include rules from JSON.

    Returns:
        Exact repository identifiers in first-seen order.
    """

    exact_repositories: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        if rule.kind != "exact":
            continue
        if rule.value in seen:
            continue
        seen.add(rule.value)
        exact_repositories.append(rule.value)
    return exact_repositories


def validate_repository_rules_for_source_mode(
    *,
    source_mode: str,
    repository_rules: Sequence[RepoSyncRepositoryRule],
) -> None:
    """Validate repository rules for source modes with strict exact-match inputs.

    Args:
        source_mode: Repo source mode selected for the runtime.
        repository_rules: Structured include rules loaded from JSON.

    Raises:
        ValueError: If explicit/filesystem modes include non-exact rules.
    """

    if source_mode not in {"explicit", "filesystem"}:
        return
    non_exact_rules = [rule.value for rule in repository_rules if rule.kind != "exact"]
    if non_exact_rules:
        raise ValueError(
            "PCG_REPOSITORY_RULES_JSON only supports exact rules when "
            f"PCG_REPO_SOURCE_MODE={source_mode!r}; "
            f"found non-exact rules: {non_exact_rules}"
        )


@dataclass(frozen=True, slots=True)
class RepoSyncConfig:
    """Runtime configuration for repository synchronization jobs.

    Attributes:
        repos_dir: Local checkout directory managed by the runtime.
        source_mode: Repository source mode such as ``githubOrg`` or ``filesystem``.
        git_auth_method: Authentication mechanism used for Git operations.
        github_org: Optional GitHub organization used for discovery.
        repositories: Explicit repository allowlist for explicit mode.
        filesystem_root: Optional source root used by filesystem mode.
        clone_depth: Clone depth used for Git fetch and clone operations.
        repo_limit: Maximum repositories to discover from GitHub.
        sync_lock_dir: Directory used as a coarse workspace lock.
        component: Observability component name for the runtime.
        repository_rules: Structured include rules loaded from
            ``PCG_REPOSITORY_RULES_JSON``.
        include_archived_repos: Whether archived GitHub repositories should be
            included during organization discovery.
    """

    repos_dir: Path
    source_mode: str
    git_auth_method: str
    github_org: str | None
    repositories: list[str]
    filesystem_root: Path | None
    clone_depth: int
    repo_limit: int
    sync_lock_dir: Path
    component: str
    repository_rules: tuple[RepoSyncRepositoryRule, ...] = ()
    include_archived_repos: bool = False

    @classmethod
    def from_env(cls, *, component: str) -> "RepoSyncConfig":
        """Create a repo-sync configuration from environment variables.

        Args:
            component: Observability component label for the runtime.

        Environment:
            ``PCG_REPOSITORY_RULES_JSON`` supplies structured exact/regex include
            rules used by the repo-sync runtime.
            ``PCG_INCLUDE_ARCHIVED_REPOS`` opts archived GitHub repositories into
            org-wide discovery when set to a truthy value.

        Returns:
            Parsed repository sync configuration.
        """

        repos_dir = Path(os.getenv("PCG_REPOS_DIR", "/data/repos"))
        source_mode = os.getenv("PCG_REPO_SOURCE_MODE", "githubOrg")
        repository_rules = parse_repository_rules_json(
            os.getenv("PCG_REPOSITORY_RULES_JSON")
        )
        validate_repository_rules_for_source_mode(
            source_mode=source_mode,
            repository_rules=repository_rules,
        )
        repositories = (
            extract_exact_repository_ids(repository_rules)
            if source_mode in {"explicit", "filesystem"}
            else []
        )
        filesystem_root = os.getenv("PCG_FILESYSTEM_ROOT")
        return cls(
            repos_dir=repos_dir,
            source_mode=source_mode,
            git_auth_method=os.getenv("PCG_GIT_AUTH_METHOD", "githubApp"),
            github_org=os.getenv("PCG_GITHUB_ORG"),
            repositories=repositories,
            filesystem_root=Path(filesystem_root) if filesystem_root else None,
            clone_depth=int(os.getenv("PCG_CLONE_DEPTH", "1")),
            repo_limit=int(os.getenv("PCG_REPO_LIMIT", "4000")),
            sync_lock_dir=repos_dir / ".pcg-sync.lock",
            component=component,
            repository_rules=repository_rules,
            include_archived_repos=(
                os.getenv("PCG_INCLUDE_ARCHIVED_REPOS", "").strip().lower()
                in {"1", "true", "yes", "on"}
            ),
        )


@dataclass(frozen=True, slots=True)
class RepoSyncResult:
    """Summary of a bootstrap or sync cycle.

    Attributes:
        discovered: Number of repositories discovered.
        cloned: Number of repositories cloned from scratch.
        updated: Number of repositories updated in place.
        skipped: Number of repositories intentionally skipped.
        failed: Number of repositories that failed clone or update.
        stale: Number of local checkouts that no longer match discovery rules.
        indexed: Number of repositories included in the resulting index.
        lock_skipped: Whether the cycle was skipped due to lock contention.
    """

    discovered: int = 0
    cloned: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    stale: int = 0
    indexed: int = 0
    lock_skipped: bool = False
