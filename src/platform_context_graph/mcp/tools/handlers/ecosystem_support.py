"""Support helpers for ecosystem MCP handlers."""

from typing import Any

from ....core.database import DatabaseManager
from ....query import repositories as repository_queries
from ....utils.debug_log import emit_log_call, warning_logger
from .ecosystem_support_provisioning import group_provisioning_source_chains


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


def _service_name_tokens(service_name: str) -> list[str]:
    """Return stable service-name tokens for cross-tool matching."""

    canonical = service_name.lower().strip()
    variants = {
        canonical,
        canonical.replace("-", "_"),
        canonical.replace("_", "-"),
    }
    return sorted(token for token in variants if token)


def _normalized_environment_names(values: list[str] | None) -> list[str]:
    """Return ordered unique environment names."""

    if not values:
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _environment_truthfulness_note(
    *,
    environments: list[str] | None,
    observed_config_environments: list[str] | None,
) -> str:
    """Return a note that distinguishes runtime-confirmed and config-only envs."""

    runtime = _normalized_environment_names(environments)
    observed = _normalized_environment_names(observed_config_environments)
    if not observed:
        return ""
    if not runtime:
        observed_phrase = ", ".join(observed)
        return (
            f"Configuration references environments {observed_phrase}, "
            "but runtime evidence has not confirmed deployed environments."
        )

    runtime_set = set(runtime)
    extra_config = [name for name in observed if name not in runtime_set]
    if not extra_config:
        return ""

    runtime_phrase = ", ".join(runtime)
    extra_phrase = ", ".join(extra_config)
    return (
        f"Confirmed runtime environments: {runtime_phrase}. "
        f"Configuration also references: {extra_phrase}."
    )


def repo_summary_note(
    *,
    limitations: list[str],
    coverage: dict[str, Any] | None,
    environments: list[str] | None = None,
    observed_config_environments: list[str] | None = None,
) -> str:
    """Return a short human-readable note for coverage and environment gaps."""

    base_note = ""
    if "graph_partial" in limitations or "content_partial" in limitations:
        base_note = (
            "Repository coverage is partial; graph/content counts may be incomplete."
        )
    elif "dns_unknown" in limitations and "entrypoint_unknown" in limitations:
        base_note = (
            "DNS and entrypoint evidence are currently unavailable for this repository."
        )
    elif "dns_unknown" in limitations:
        base_note = "DNS evidence is currently unavailable for this repository."
    elif "entrypoint_unknown" in limitations:
        base_note = (
            "Entrypoint evidence is currently unavailable for this repository."
        )
    elif "finalization_incomplete" in limitations:
        finalization_status = str(
            (coverage or {}).get("finalization_status") or ""
        ).strip()
        status_phrase = finalization_status or "pending"
        base_note = (
            f"Repository finalization is {status_phrase}; deployment and relationship "
            "summaries may still be incomplete."
        )
    elif coverage and coverage.get("completeness_state") == "failed":
        base_note = (
            "Repository coverage failed; runtime and deployment summaries may be incomplete."
        )
    elif limitations:
        base_note = "Repository context has known limitations."

    env_note = _environment_truthfulness_note(
        environments=environments,
        observed_config_environments=observed_config_environments,
    )
    if base_note and env_note:
        return f"{base_note} {env_note}"
    return base_note or env_note


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
    service_name_tokens = _service_name_tokens(canonical_name)
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
            RETURN app.name as app_name,
                   app[$project_key] as project,
                   app[$dest_namespace_key] as namespace,
                   app[$source_path_key] as source_path
        """,
            name=canonical_name,
            project_key="project",
            dest_namespace_key="dest_namespace",
            source_path_key="source_path",
        ).data()

        argocd_appsets = session.run(
            """
            MATCH (app:ArgoCDApplicationSet)
            WHERE app.name CONTAINS $name
               OR coalesce(app[$source_paths_key], '') CONTAINS $name
               OR coalesce(app[$source_roots_key], '') CONTAINS $name
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
        ).data()
        resolved_source_repo_names = _source_repo_name_hints(
            source_repositories=source_repositories,
            argocd_apps=argocd_apps,
            argocd_appsets=argocd_appsets,
        )

        repo_k8s_resources = session.run(
            """
            MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(k:K8sResource)
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
                MATCH (repo:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(k:K8sResource)
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
            MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(claim:CrossplaneClaim)
            WHERE r.name CONTAINS $name
            RETURN claim.name as claim_name,
                   claim.kind as claim_kind,
                   f.relative_path as file
        """,
            name=canonical_name,
        ).data()

        terraform = session.run(
            """
            MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(tf:TerraformResource)
            WHERE r.name CONTAINS $name
               OR (
                    r.id IN $provisioned_repo_ids
                    AND any(
                        token IN $service_name_tokens
                        WHERE toLower(coalesce(tf.name, '')) CONTAINS token
                           OR toLower(coalesce(f.relative_path, '')) CONTAINS token
                    )
               )
            RETURN tf.name as name,
                   tf.resource_type as resource_type,
                   f.relative_path as file,
                   r.name as repository
            ORDER BY r.name, tf.resource_type, tf.name
            LIMIT 100
        """,
            name=canonical_name,
            provisioned_repo_ids=provisioned_repo_ids,
            service_name_tokens=service_name_tokens,
        ).data()

        tf_modules_raw = session.run(
            """
            MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(mod:TerraformModule)
            OPTIONAL MATCH (mod)-[:USES_MODULE]->(source_repo:Repository)
            WHERE r.name CONTAINS $name
               OR (
                    r.id IN $provisioned_repo_ids
                    AND any(
                        token IN $service_name_tokens
                        WHERE toLower(coalesce(mod.name, '')) CONTAINS token
                           OR toLower(coalesce(f.relative_path, '')) CONTAINS token
                    )
               )
            RETURN mod.name as name,
                   mod.source as source,
                   mod.version as version,
                   source_repo.name as source_repository,
                   r.name as repository
            ORDER BY r.name, mod.name
            LIMIT 100
        """,
            name=canonical_name,
            provisioned_repo_ids=provisioned_repo_ids,
            service_name_tokens=service_name_tokens,
        ).data()

        terragrunt_configs = session.run(
            """
            MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(tg:TerragruntConfig)
            OPTIONAL MATCH (tg)-[:USES_MODULE]->(source_repo:Repository)
            WHERE r.name CONTAINS $name
               OR r.id IN $provisioned_repo_ids
            RETURN tg.name as name,
                   tg[$terraform_source_key] as terraform_source,
                   f.relative_path as file,
                   r.name as repository,
                   source_repo.name as source_repository
            ORDER BY r.name, f.relative_path, tg.name
            LIMIT 100
        """,
            name=canonical_name,
            provisioned_repo_ids=provisioned_repo_ids,
            terraform_source_key="terraform_source",
        ).data()

    k8s_resources = _dedupe_rows(repo_k8s_resources + deployed_k8s_resources)
    tf_modules = [
        {
            "name": row.get("name"),
            "source": row.get("source"),
            "version": row.get("version"),
            "repository": row.get("repository"),
        }
        for row in _dedupe_rows(tf_modules_raw)
    ]
    terragrunt_configs = _dedupe_rows(terragrunt_configs)
    provisioning_source_chains = group_provisioning_source_chains(
        terraform_modules=tf_modules_raw,
        terragrunt_configs=terragrunt_configs,
    )

    limitations = list(context.get("limitations") or [])
    result = {
        "repository": dict(repo),
        "argocd_applications": argocd_apps,
        "argocd_applicationsets": argocd_appsets,
        "k8s_resources": k8s_resources,
        "crossplane_claims": claims,
        "terraform_resources": terraform,
        "terraform_modules": tf_modules,
        "terragrunt_configs": terragrunt_configs,
        "provisioning_source_chains": provisioning_source_chains,
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
        "observed_config_environments": context.get(
            "observed_config_environments", []
        ),
        "delivery_workflows": context.get("delivery_workflows", {}),
        "delivery_paths": context.get("delivery_paths", []),
        "api_surface": context.get("api_surface", {}),
        "hostnames": context.get("hostnames", []),
        "limitations": limitations,
    }
    if limitations:
        result["note"] = repo_summary_note(
            limitations=limitations,
            coverage=context.get("coverage"),
            environments=result["environments"],
            observed_config_environments=result["observed_config_environments"],
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
    else:
        note = repo_summary_note(
            limitations=[],
            coverage=context.get("coverage"),
            environments=result["environments"],
            observed_config_environments=result["observed_config_environments"],
        )
        if note:
            result["note"] = note
    return result
