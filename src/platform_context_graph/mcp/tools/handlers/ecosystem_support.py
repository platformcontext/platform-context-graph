"""Support helpers for ecosystem MCP handlers."""

from typing import Any

from ....core.database import DatabaseManager
from ....query import repositories as repository_queries
from ....utils.debug_log import emit_log_call, warning_logger


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return rows with duplicates removed while preserving order."""
    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(sorted((str(k), repr(v)) for k, v in row.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _canonical_source_repositories(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the deduplicated config and deployment source repositories."""

    rows = [
        *list(context.get("deploys_from") or []),
        *list(context.get("discovers_config_in") or []),
    ]
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        identity = str(row.get("id") or row.get("name") or "").strip()
        if not identity or identity in seen:
            continue
        seen.add(identity)
        deduped.append(row)
    return deduped


def _split_csv(value: Any) -> list[str]:
    """Return non-empty trimmed CSV tokens from one raw value."""

    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _source_repo_name_hints(
    *,
    source_repositories: list[dict[str, Any]],
    argocd_apps: list[dict[str, Any]],
    argocd_appsets: list[dict[str, Any]],
) -> list[str]:
    """Return portable repository-name hints from canonical and ArgoCD context."""

    names = {
        str(row["name"]).strip()
        for row in source_repositories
        if row.get("name")
    }
    for row in [*argocd_apps, *argocd_appsets]:
        for raw_repo in _split_csv(row.get("source_repos")):
            candidate = raw_repo.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
            if candidate:
                names.add(candidate)
    return sorted(names)


def repo_summary_note(
    *, limitations: list[str], coverage: dict[str, Any] | None
) -> str:
    """Return a short human-readable note for limitation codes."""

    if "graph_partial" in limitations or "content_partial" in limitations:
        return "Repository coverage is partial; graph/content counts may be incomplete."
    if "dns_unknown" in limitations and "entrypoint_unknown" in limitations:
        return "DNS and entrypoint evidence are currently unavailable for this repository."
    if "dns_unknown" in limitations:
        return "DNS evidence is currently unavailable for this repository."
    if "entrypoint_unknown" in limitations:
        return "Entrypoint evidence is currently unavailable for this repository."
    if coverage and coverage.get("completeness_state") == "failed":
        return "Repository coverage failed; runtime and deployment summaries may be incomplete."
    return "Repository context has known limitations."


def trace_deployment_chain(
    db_manager: DatabaseManager,
    service_name: str,
) -> dict[str, Any]:
    """Trace the full deployment chain for a service."""
    context = repository_queries.get_repository_context(
        db_manager,
        repo_id=service_name,
    )
    if "error" in context:
        return context

    canonical_repository = context.get("repository") or {}
    canonical_name = str(canonical_repository.get("name") or service_name)
    canonical_name_lc = canonical_name.lower()
    source_repositories = _canonical_source_repositories(context)
    source_repo_ids = [str(row["id"]) for row in source_repositories if row.get("id")]
    source_repo_names = [
        str(row["name"]) for row in source_repositories if row.get("name")
    ]
    provisioned_by = list(context.get("provisioned_by") or [])
    provisioned_repo_ids = [
        str(row["id"]) for row in provisioned_by if row.get("id")
    ]
    driver = db_manager.get_driver()

    with driver.session() as session:
        repo = session.run(
            "MATCH (r:Repository) "
            "WHERE r.name CONTAINS $name "
            "RETURN r.name as name, r.path as path "
            "LIMIT 1",
            name=canonical_name,
        ).single()

        if not repo:
            repo = {
                "name": canonical_name,
                "path": canonical_repository.get("local_path")
                or canonical_repository.get("path"),
            }

        argocd_apps = session.run(
            """
            MATCH (app:ArgoCDApplication)
            WHERE app.name CONTAINS $name
               OR coalesce(app[$source_path_key], '') CONTAINS $name
               OR any(source_repo_name IN $source_repo_names
                      WHERE coalesce(app[$source_repo_key], '') CONTAINS source_repo_name)
            RETURN app.name as app_name,
                   app[$project_key] as project,
                   app[$dest_namespace_key] as namespace,
                   app[$source_path_key] as source_path
        """,
            name=canonical_name,
            project_key="project",
            dest_namespace_key="dest_namespace",
            source_path_key="source_path",
            source_repo_key="source_repo",
            source_repo_names=source_repo_names,
        ).data()

        argocd_appsets = session.run(
            """
            MATCH (app:ArgoCDApplicationSet)
            WHERE app.name CONTAINS $name
               OR coalesce(app[$source_paths_key], '') CONTAINS $name
               OR coalesce(app[$source_roots_key], '') CONTAINS $name
               OR any(source_repo_name IN $source_repo_names
                      WHERE coalesce(app[$source_repos_key], '') CONTAINS source_repo_name)
            RETURN app.name as app_name,
                   app[$project_key] as project,
                   app.namespace as namespace,
                   app[$dest_namespace_key] as dest_namespace,
                   app[$source_repos_key] as source_repos,
                   app[$source_paths_key] as source_paths,
                   app[$source_roots_key] as source_roots
        """,
            name=canonical_name,
            project_key="project",
            dest_namespace_key="dest_namespace",
            source_repos_key="source_repos",
            source_paths_key="source_paths",
            source_roots_key="source_roots",
            source_repo_names=source_repo_names,
        ).data()
        resolved_source_repo_names = _source_repo_name_hints(
            source_repositories=source_repositories,
            argocd_apps=argocd_apps,
            argocd_appsets=argocd_appsets,
        )

        repo_k8s_resources = session.run(
            """
            MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(k:K8sResource)
            WHERE r.name CONTAINS $name
            RETURN k.name as name, k.kind as kind,
                   k.namespace as namespace,
                   f.relative_path as file
        """,
            name=canonical_name,
        ).data()

        deployed_k8s_resources = []
        if source_repo_ids or resolved_source_repo_names:
            deployed_k8s_resources = session.run(
                """
                MATCH (repo:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(k:K8sResource)
                WHERE (repo.id IN $source_repo_ids OR repo.name IN $source_repo_names)
                  AND (
                      toLower(coalesce(f.relative_path, '')) CONTAINS $service_name_lc
                      OR toLower(coalesce(k.name, '')) CONTAINS $service_name_lc
                  )
                RETURN DISTINCT
                       k.name as name,
                       k.kind as kind,
                       k.namespace as namespace,
                       f.relative_path as file,
                       repo.name as repository,
                       $name as deployed_by
                ORDER BY repo.name, f.relative_path, k.name
            """,
                source_repo_ids=source_repo_ids,
                source_repo_names=resolved_source_repo_names,
                service_name_lc=canonical_name_lc,
                name=canonical_name,
            ).data()

        claims = session.run(
            """
            MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(claim:CrossplaneClaim)
            WHERE r.name CONTAINS $name
            RETURN claim.name as claim_name,
                   claim.kind as claim_kind,
                   f.relative_path as file
        """,
            name=canonical_name,
        ).data()

        terraform = session.run(
            """
            MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(tf:TerraformResource)
            WHERE r.name CONTAINS $name OR r.id IN $provisioned_repo_ids
            RETURN tf.name as name,
                   tf.resource_type as resource_type,
                   f.relative_path as file,
                   r.name as repository
            ORDER BY r.name, tf.resource_type, tf.name
            LIMIT 100
        """,
            name=canonical_name,
            provisioned_repo_ids=provisioned_repo_ids,
        ).data()

        tf_modules = session.run(
            """
            MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(mod:TerraformModule)
            WHERE r.name CONTAINS $name OR r.id IN $provisioned_repo_ids
            RETURN mod.name as name,
                   mod.source as source,
                   mod.version as version,
                   r.name as repository
            ORDER BY r.name, mod.name
            LIMIT 100
        """,
            name=canonical_name,
            provisioned_repo_ids=provisioned_repo_ids,
        ).data()

    k8s_resources = _dedupe_rows(repo_k8s_resources + deployed_k8s_resources)

    limitations = list(context.get("limitations") or [])
    result = {
        "repository": dict(repo),
        "argocd_applications": argocd_apps,
        "argocd_applicationsets": argocd_appsets,
        "k8s_resources": k8s_resources,
        "crossplane_claims": claims,
        "terraform_resources": terraform,
        "terraform_modules": tf_modules,
        "coverage": context.get("coverage"),
        "platforms": context.get("platforms", []),
        "deploys_from": context.get("deploys_from", []),
        "discovers_config_in": context.get("discovers_config_in", []),
        "provisioned_by": context.get("provisioned_by", []),
        "provisions_dependencies_for": context.get(
            "provisions_dependencies_for", []
        ),
        "deployment_chain": context.get("deployment_chain", []),
        "environments": context.get("environments", []),
        "api_surface": context.get("api_surface", {}),
        "hostnames": context.get("hostnames", []),
        "limitations": limitations,
    }
    if limitations:
        result["note"] = repo_summary_note(
            limitations=limitations,
            coverage=context.get("coverage"),
        )
        emit_log_call(
            warning_logger,
            "Deployment chain assembled with known limitations",
            event_name="deployment.chain.limitations",
            extra_keys={
                "repo_name": canonical_name,
                "limitations": limitations,
                "platform_count": len(result["platforms"]),
                "deployment_chain_length": len(result["deployment_chain"]),
            },
        )
    return result
