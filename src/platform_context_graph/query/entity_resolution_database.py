"""Live-database candidate builders for canonical entity resolution."""

from __future__ import annotations

import re
from typing import Any

from .context.support import infer_workload_kind

_TOKEN_RE = re.compile(r"[a-z0-9_.:/-]+")


def _search_terms(query: str) -> list[str]:
    """Return normalized query terms used to trim live-database candidate scans."""
    normalized = query.strip().lower()
    if not normalized:
        return []
    terms = _TOKEN_RE.findall(normalized)
    return list(dict.fromkeys(terms or [normalized]))


def _name_match(field: str) -> str:
    """Return the Cypher predicate used to filter candidate names."""
    return f"ANY(term IN $terms WHERE toLower(coalesce({field}, '')) CONTAINS term)"


def _aliases(*groups: list[str]) -> list[str]:
    """Return a stable de-duplicated alias list."""
    aliases: list[str] = []
    for group in groups:
        for value in group:
            if not value or value in aliases:
                continue
            aliases.append(value)
    return aliases


def db_workload_entities(database: Any, *, query: str, repo_id: str | None) -> list[dict[str, Any]]:
    """Return synthetic workload entities inferred from live repo, runtime, and Argo data."""
    terms = _search_terms(query)
    if not terms:
        return []

    driver = database.get_driver()
    with driver.session() as session:
        workload_rows = session.run(
            f"""
            MATCH (w:Workload)
            WHERE ({_name_match('w.name')} OR {_name_match('w.id')})
              AND ($repo_id IS NULL OR w.repo_id = $repo_id)
            OPTIONAL MATCH (repo:Repository {{id: w.repo_id}})
            RETURN w.id as id,
                   w.name as name,
                   w.kind as kind,
                   w.repo_id as repo_id,
                   repo.name as repo_name,
                   coalesce(repo.repo_slug, '') as repo_slug,
                   coalesce(repo.remote_url, '') as remote_url
            """,
            terms=terms,
            repo_id=repo_id,
        ).data()
        instance_rows = session.run(
            f"""
            MATCH (i:WorkloadInstance)
            WHERE ({_name_match('i.name')} OR {_name_match('i.id')} OR {_name_match('i.environment')})
              AND ($repo_id IS NULL OR i.repo_id = $repo_id)
            OPTIONAL MATCH (repo:Repository {{id: i.repo_id}})
            RETURN i.id as id,
                   i.name as name,
                   i.kind as kind,
                   i.environment as environment,
                   i.workload_id as workload_id,
                   i.repo_id as repo_id,
                   repo.name as repo_name,
                   coalesce(repo.repo_slug, '') as repo_slug,
                   coalesce(repo.remote_url, '') as remote_url
            """,
            terms=terms,
            repo_id=repo_id,
        ).data()

    entities: list[dict[str, Any]] = []
    for row in workload_rows:
        name = str(row.get("name") or "").strip()
        entity_id = str(row.get("id") or "").strip()
        if not entity_id or not name:
            continue
        entities.append(
            {
                "id": entity_id,
                "type": "workload",
                "kind": row.get("kind") or "service",
                "name": name,
                "repo_id": row.get("repo_id"),
                "aliases": _aliases(
                    [name, f"{name} service"],
                    [row.get("repo_name", ""), row.get("repo_slug", ""), row.get("remote_url", "")],
                ),
            }
        )

    for row in instance_rows:
        name = str(row.get("name") or "").strip()
        entity_id = str(row.get("id") or "").strip()
        environment = str(row.get("environment") or "").strip()
        if not entity_id or not name or not environment:
            continue
        entities.append(
            {
                "id": entity_id,
                "type": "workload_instance",
                "kind": row.get("kind") or "service",
                "name": name,
                "environment": environment,
                "workload_id": row.get("workload_id") or f"workload:{name}",
                "repo_id": row.get("repo_id"),
                "aliases": _aliases(
                    [f"{name} {environment}", name],
                    [row.get("repo_name", ""), row.get("repo_slug", ""), row.get("remote_url", "")],
                ),
            }
        )

    if entities:
        return entities

    with driver.session() as session:
        resource_rows = session.run(
            f"""
            MATCH (repo:Repository)-[:CONTAINS*]->(:File)-[:CONTAINS]->(k:K8sResource)
            WHERE {_name_match('k.name')} AND ($repo_id IS NULL OR repo.id = $repo_id)
            RETURN k.name as name,
                   collect(DISTINCT toLower(coalesce(k.kind, ''))) as resource_kinds,
                   collect(DISTINCT coalesce(k.namespace, '')) as namespaces,
                   collect(DISTINCT repo.id) as repo_ids,
                   collect(DISTINCT repo.name) as repo_names,
                   collect(DISTINCT coalesce(repo.repo_slug, '')) as repo_slugs,
                   collect(DISTINCT coalesce(repo.remote_url, '')) as remote_urls
            """,
            terms=terms,
            repo_id=repo_id,
        ).data()
        argocd_rows = session.run(
            f"""
            MATCH (app)
            WHERE (app:ArgoCDApplication OR app:ArgoCDApplicationSet) AND {_name_match('app.name')}
            OPTIONAL MATCH (app)-[:SOURCES_FROM]->(repo:Repository)
            WITH app.name as name,
                 collect(DISTINCT CASE
                     WHEN app:ArgoCDApplicationSet THEN 'applicationset'
                     ELSE 'application'
                 END) as app_kinds,
                 collect(DISTINCT repo.id) as repo_ids,
                 collect(DISTINCT repo.name) as repo_names,
                 collect(DISTINCT coalesce(repo.repo_slug, '')) as repo_slugs,
                 collect(DISTINCT coalesce(repo.remote_url, '')) as remote_urls
            WHERE $repo_id IS NULL OR $repo_id IN repo_ids
            RETURN name, app_kinds, repo_ids, repo_names, repo_slugs, remote_urls
            """,
            terms=terms,
            repo_id=repo_id,
        ).data()

    aggregated: dict[str, dict[str, set[str]]] = {}
    for row in resource_rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        bucket = aggregated.setdefault(
            name,
            {
                "resource_kinds": set(),
                "namespaces": set(),
                "repo_ids": set(),
                "repo_names": set(),
                "repo_slugs": set(),
                "remote_urls": set(),
                "app_kinds": set(),
            },
        )
        bucket["resource_kinds"].update(filter(None, row.get("resource_kinds", [])))
        bucket["namespaces"].update(filter(None, row.get("namespaces", [])))
        bucket["repo_ids"].update(filter(None, row.get("repo_ids", [])))
        bucket["repo_names"].update(filter(None, row.get("repo_names", [])))
        bucket["repo_slugs"].update(filter(None, row.get("repo_slugs", [])))
        bucket["remote_urls"].update(filter(None, row.get("remote_urls", [])))
    for row in argocd_rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        bucket = aggregated.setdefault(
            name,
            {
                "resource_kinds": set(),
                "namespaces": set(),
                "repo_ids": set(),
                "repo_names": set(),
                "repo_slugs": set(),
                "remote_urls": set(),
                "app_kinds": set(),
            },
        )
        bucket["app_kinds"].update(filter(None, row.get("app_kinds", [])))
        bucket["repo_ids"].update(filter(None, row.get("repo_ids", [])))
        bucket["repo_names"].update(filter(None, row.get("repo_names", [])))
        bucket["repo_slugs"].update(filter(None, row.get("repo_slugs", [])))
        bucket["remote_urls"].update(filter(None, row.get("remote_urls", [])))

    entities: list[dict[str, Any]] = []
    for name, metadata in aggregated.items():
        kind = infer_workload_kind(name, sorted(metadata["resource_kinds"]))
        aliases = _aliases(
            [name, f"{name} service"],
            sorted(metadata["repo_names"]),
            sorted(metadata["repo_slugs"]),
            sorted(metadata["remote_urls"]),
        )
        canonical_workload_id = f"workload:{name}"
        entity: dict[str, Any] = {
            "id": canonical_workload_id,
            "type": "workload",
            "kind": kind,
            "name": name,
            "aliases": aliases,
        }
        if len(metadata["repo_ids"]) == 1:
            entity["repo_id"] = next(iter(metadata["repo_ids"]))
        entities.append(entity)
        for namespace in sorted(metadata["namespaces"]):
            entities.append(
                {
                    "id": f"workload-instance:{name}:{namespace}",
                    "type": "workload_instance",
                    "kind": kind,
                    "name": name,
                    "environment": namespace,
                    "workload_id": canonical_workload_id,
                    "repo_id": entity.get("repo_id"),
                    "aliases": _aliases(
                        [f"{name} {namespace}"],
                        aliases,
                    ),
                }
            )
    return entities


__all__ = ["db_workload_entities"]
