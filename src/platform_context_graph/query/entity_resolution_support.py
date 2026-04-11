"""Shared helpers for entity-resolution matching and fixture-backed queries."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ..domain import (
    AliasMetadata,
    EntityRef,
    EntityType,
    EvidenceItem,
    InferenceMetadata,
    ResolveEntityMatch,
    WorkloadKind,
)
from .story_shared import portable_story_value

_TOKEN_RE = re.compile(r"[a-z0-9_.:/-]+")


def load_fixture_graph(database: Any) -> dict[str, Any] | None:
    """Load fixture graph data when the query runs against fixture inputs."""

    if isinstance(database, dict):
        return database
    if isinstance(database, Path):
        return json.loads(database.read_text())
    if isinstance(database, str):
        path = Path(database)
        if path.exists() and path.suffix == ".json":
            return json.loads(path.read_text())
    return None


def canonical_ref(entity: dict[str, Any]) -> EntityRef:
    """Convert a raw entity mapping into a canonical entity reference."""

    entity_type = EntityType(entity["type"])
    raw_path = entity.get("path")
    local_path = entity.get("local_path")
    if (
        entity_type == EntityType.repository
        and local_path is None
        and raw_path is not None
    ):
        local_path = raw_path
        raw_path = None
    return EntityRef(
        id=entity["id"],
        type=entity_type,
        kind=entity.get("kind"),
        name=entity["name"],
        environment=(
            entity.get("environment")
            if entity_type in {EntityType.environment, EntityType.workload_instance}
            else None
        ),
        workload_id=entity.get("workload_id"),
        path=raw_path,
        relative_path=entity.get("relative_path"),
        local_path=local_path,
        repo_slug=entity.get("repo_slug"),
        remote_url=entity.get("remote_url"),
        has_remote=entity.get("has_remote"),
    )


def match_terms(entity: dict[str, Any]) -> list[tuple[str, str]]:
    """Collect searchable terms used for repository and entity matching."""

    terms: list[tuple[str, str]] = [("id", entity["id"]), ("name", entity["name"])]
    if path := entity.get("path"):
        terms.append(("path", path))
    if relative_path := entity.get("relative_path"):
        terms.append(("relative_path", relative_path))
    if local_path := entity.get("local_path"):
        terms.append(("local_path", local_path))
    if repo_slug := entity.get("repo_slug"):
        terms.append(("repo_slug", repo_slug))
    if remote_url := entity.get("remote_url"):
        terms.append(("remote_url", remote_url))
    for alias in entity.get("aliases", []):
        terms.append(("alias", alias))
    if entity["type"] == "workload" and entity.get("kind") == "service":
        terms.append(("service", f"{entity['name']} service"))
    if environment := entity.get("environment"):
        terms.append(("environment", f"{entity['name']} {environment}"))
    return terms


def edge_evidence(graph: dict[str, Any], entity_id: str) -> list[EvidenceItem]:
    """Collect evidence items attached to graph edges touching an entity."""

    evidence: list[EvidenceItem] = []
    for edge in graph.get("edges", []):
        if edge.get("from") != entity_id and edge.get("to") != entity_id:
            continue
        for item in edge.get("evidence", []):
            evidence.append(
                EvidenceItem(
                    source=item.get("source"),
                    detail=item.get("detail"),
                    weight=item.get("weight"),
                )
            )
    return evidence


def entity_matches_filters(
    entity: dict[str, Any],
    *,
    allowed_types: set[EntityType],
    allowed_kinds: set[WorkloadKind],
    environment: str | None,
    repo_id: str | None,
) -> bool:
    """Return whether an entity satisfies type, kind, environment, and repo filters."""

    entity_type = EntityType(entity["type"])
    if allowed_types and entity_type not in allowed_types:
        return False

    entity_kind = entity.get("kind")
    if allowed_kinds:
        if entity_kind is None or WorkloadKind(entity_kind) not in allowed_kinds:
            return False

    if environment:
        entity_environment = entity.get("environment")
        normalized_environment = (environment or "").strip().lower()
        if entity_environment and str(entity_environment).strip().lower() != normalized_environment:
            return False
        if entity["type"] == "workload" and entity_environment is None:
            pass
        elif entity_environment is None and entity["type"] != "repository":
            return False

    if repo_id:
        if entity["type"] == "repository":
            return entity["id"] == repo_id
        return entity.get("repo_id") == repo_id

    return True


def score_match(
    entity: dict[str, Any],
    *,
    query: str,
    exact: bool,
) -> tuple[float, str | None, str | None]:
    """Score one entity against a user query and record the winning term."""

    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return 0.0, None, None

    best_score = 0.0
    best_source: str | None = None
    best_value: str | None = None

    for source, value in match_terms(entity):
        normalized_value = (value or "").strip().lower()
        if exact:
            if normalized_query == normalized_value:
                score = 1.0 if source == "id" else 0.97
            else:
                continue
        else:
            query_tokens = _TOKEN_RE.findall(normalized_query)
            value_tokens = _TOKEN_RE.findall(normalized_value)
            overlap = sum(
                token in value_tokens or token in normalized_value
                for token in query_tokens
            )
            if overlap == 0:
                ratio = SequenceMatcher(
                    None, normalized_query, normalized_value
                ).ratio()
                if ratio < 0.55:
                    continue
                score = 0.45 + (ratio * 0.35)
            else:
                coverage = overlap / max(len(query_tokens), 1)
                ratio = SequenceMatcher(
                    None, normalized_query, normalized_value
                ).ratio()
                score = 0.5 + (coverage * 0.3) + (ratio * 0.15)
                if normalized_query in normalized_value:
                    score += 0.05
                if normalized_value.startswith(normalized_query):
                    score += 0.03

            if source == "id":
                score += 0.08
            elif source == "name":
                score += 0.05
            elif source in {"alias", "service"}:
                score += 0.02

        if score > best_score:
            best_score = min(score, 1.0)
            best_source = source
            best_value = value

    return best_score, best_source, best_value


def build_match(
    entity: dict[str, Any],
    *,
    score: float,
    source: str | None,
    matched_value: str | None,
    graph: dict[str, Any] | None,
    query: str,
) -> dict[str, Any]:
    """Construct the serialized entity-resolution match payload."""

    inference: InferenceMetadata | None = None
    alias: AliasMetadata | None = None
    if source and source != "id":
        evidence = edge_evidence(graph or {}, entity["id"])
        if not evidence and matched_value:
            evidence = [
                EvidenceItem(
                    source="entity-alias",
                    detail=f"Matched {source} '{matched_value}'",
                    weight=round(max(score - 0.05, 0.1), 2),
                )
            ]
        inference = InferenceMetadata(
            confidence=round(min(score, 0.99), 2),
            reason=f"Matched {source} '{matched_value}' to canonical {entity['id']}",
            evidence=evidence,
        )
    if (
        entity["type"] == "workload"
        and entity.get("kind") == "service"
        and "service" in (query or "").strip().lower()
    ):
        alias = AliasMetadata(
            requested_as="service",
            canonical_type=EntityType.workload,
            confidence=round(min(score, 0.99), 2),
            reason="Service-oriented lookup normalized onto canonical workload identity",
        )
    match = ResolveEntityMatch(
        ref=canonical_ref(entity),
        score=round(score, 4),
        inference=inference,
        match_type=source,
        alias=alias,
    )
    return portable_story_value(match.model_dump(mode="json", exclude_none=True))


def fixture_matches(
    graph: dict[str, Any],
    *,
    query: str,
    allowed_types: set[EntityType],
    allowed_kinds: set[WorkloadKind],
    environment: str | None,
    repo_id: str | None,
    exact: bool,
    limit: int,
) -> dict[str, Any]:
    """Resolve entities against fixture graph data."""

    matches: list[dict[str, Any]] = []
    for entity in graph.get("entities", []):
        if not entity_matches_filters(
            entity,
            allowed_types=allowed_types,
            allowed_kinds=allowed_kinds,
            environment=environment,
            repo_id=repo_id,
        ):
            continue
        score, source, matched_value = score_match(entity, query=query, exact=exact)
        if score <= 0:
            continue
        matches.append(
            build_match(
                entity,
                score=score,
                source=source,
                matched_value=matched_value,
                graph=graph,
                query=query,
            )
        )
    matches.sort(key=lambda item: (-item["score"], item["ref"]["id"]))
    return {"matches": matches[:limit]}


__all__ = [
    "build_match",
    "entity_matches_filters",
    "fixture_matches",
    "load_fixture_graph",
    "score_match",
]
