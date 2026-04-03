"""Helper utilities for cross-repository matching and linking."""

from __future__ import annotations

from typing import Any

from ..repository_identity import normalize_remote_url, repo_slug_from_remote_url


def clean_text(value: Any) -> str | None:
    """Return a trimmed string for matching or ``None`` for empty values."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def repository_match_keys(repository: dict[str, Any]) -> list[str]:
    """Return the lookup keys that should identify one repository node."""

    keys: list[str] = []
    for candidate in (
        normalize_remote_url(repository.get("remote_url")),
        repo_slug_from_remote_url(repository.get("remote_url")),
        normalize_remote_url(repository.get("repo_slug")),
        repo_slug_from_remote_url(repository.get("repo_slug")),
        clean_text(repository.get("name")),
    ):
        if candidate and candidate not in keys:
            keys.append(candidate)
    return keys


def candidate_repository_references(reference: str) -> list[str]:
    """Return repository-level candidates from one raw source reference."""

    candidates: list[str] = []

    def add(candidate: str | None) -> None:
        """Append one cleaned candidate reference while preserving order."""

        cleaned = clean_text(candidate)
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    add(reference)

    if reference.startswith("git::"):
        add(reference[len("git::") :])

    for candidate in list(candidates):
        without_query = candidate.split("?", 1)[0]
        add(without_query)

        if "://" in without_query:
            scheme_sep = without_query.find("://") + 3
            module_sep = without_query.find("//", scheme_sep)
            if module_sep != -1:
                add(without_query[:module_sep])
        elif ".git//" in without_query:
            add(without_query.split(".git//", 1)[0] + ".git")

    return candidates


def reference_match_keys(reference: str | None) -> list[str]:
    """Return ranked lookup keys for one remote repository reference."""

    cleaned_reference = clean_text(reference)
    if cleaned_reference is None:
        return []

    keys: list[str] = []
    for reference_candidate in candidate_repository_references(cleaned_reference):
        for candidate in (
            normalize_remote_url(reference_candidate),
            repo_slug_from_remote_url(reference_candidate),
            reference_candidate,
        ):
            if candidate and candidate not in keys:
                keys.append(candidate)
    return keys


def repository_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Index repository rows by normalized remote and slug keys."""

    index: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for key in repository_match_keys(row):
            index.setdefault(key, []).append(row)
    return index


def first_matching_repositories(
    reference: str | None,
    repository_lookup: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Return the best matching repository rows for one source reference."""

    for key in reference_match_keys(reference):
        rows = repository_lookup.get(key)
        if rows:
            seen: set[str] = set()
            matches: list[dict[str, Any]] = []
            for row in rows:
                repo_id = clean_text(row.get("id"))
                if repo_id is None or repo_id in seen:
                    continue
                seen.add(repo_id)
                matches.append(row)
            return matches
    return []


def split_references(raw_references: str | None) -> list[str]:
    """Return normalized source references from a comma-separated field."""

    if raw_references is None:
        return []
    return [
        reference
        for reference in (clean_text(part) for part in raw_references.split(","))
        if reference is not None
    ]


def reference_links(
    reference_rows: list[dict[str, Any]],
    repository_lookup: dict[str, list[dict[str, Any]]],
) -> list[dict[str, str]]:
    """Resolve raw source references to repository link payloads."""

    links: list[dict[str, str]] = []
    seen_links: set[tuple[str, str]] = set()
    for row in reference_rows:
        source = clean_text(row.get("source"))
        if source is None:
            continue
        for repo in first_matching_repositories(source, repository_lookup):
            repo_id = clean_text(repo.get("id"))
            if repo_id is None:
                continue
            link_key = (source, repo_id)
            if link_key in seen_links:
                continue
            seen_links.add(link_key)
            links.append({"source": source, "repo_id": repo_id})
    return links
