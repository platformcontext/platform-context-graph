"""Support helpers for ecosystem MCP handlers."""

from typing import Any

from ....core.database import DatabaseManager
from ....query import repositories as repository_queries
from ....query.story_documentation import (
    build_documentation_overview,
    build_graph_context_evidence,
    collect_documentation_evidence,
)
from ....query.story_gitops import build_gitops_overview
from ....query.story_shared import portable_story_value
from ....query.story_support import build_support_overview
from ....utils.debug_log import emit_log_call, warning_logger
from .ecosystem_support_overview import (
    build_deployment_overview,
    build_story_lines,
)
from .ecosystem_support_provisioning import group_provisioning_source_chains
from .ecosystem_support_trace_helpers import (
    _canonical_source_repositories,
    _dedupe_rows,
    _direct_deployment_chain_rows,
    _direct_repo_rows,
    _focused_trace_note,
    _service_name_tokens,
    _source_repo_name_hints,
    _trace_truncation,
    repo_summary_note,
)


def trace_deployment_chain(
    db_manager: DatabaseManager,
    service_name: str,
    *,
    direct_only: bool = True,
    max_depth: int | None = None,
    include_related_module_usage: bool = False,
) -> dict[str, Any]:
    """Trace the deployment chain for a service."""
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
    provisioned_repo_ids = [str(row["id"]) for row in provisioned_by if row.get("id")]
    driver = db_manager.get_driver()

    with driver.session() as session:
        repo = session.run(
            "MATCH (r:Repository) "
            "WHERE r.name CONTAINS $name "
            "RETURN r.id as id, r.name as name "
            "LIMIT 1",
            name=canonical_name,
        ).single()

        if not repo:
            repo = {
                "id": canonical_repository.get("id"),
                "name": canonical_name,
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
                   mod.deployment_name as deployment_name,
                   mod.repo_name as repo_name,
                   mod.create_deploy as create_deploy,
                   mod.cluster_name as cluster_name,
                   mod.zone_id as zone_id,
                   mod.deploy_entry_point as deploy_entry_point,
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
    if direct_only:
        k8s_resources = _dedupe_rows(repo_k8s_resources)
    tf_modules = [
        {
            "name": row.get("name"),
            "source": row.get("source"),
            "version": row.get("version"),
            "deployment_name": row.get("deployment_name"),
            "repo_name": row.get("repo_name"),
            "create_deploy": row.get("create_deploy"),
            "cluster_name": row.get("cluster_name"),
            "zone_id": row.get("zone_id"),
            "deploy_entry_point": row.get("deploy_entry_point"),
            "repository": row.get("repository"),
            "source_repository": row.get("source_repository"),
        }
        for row in _dedupe_rows(tf_modules_raw)
    ]
    if include_related_module_usage:
        tf_modules = _dedupe_rows(tf_modules)
    else:
        tf_modules = _direct_repo_rows(
            tf_modules,
            repository_name=canonical_name,
        )
    terraform_resources = _dedupe_rows(terraform)
    if direct_only or not include_related_module_usage:
        terraform_resources = _direct_repo_rows(
            terraform_resources,
            repository_name=canonical_name,
        )
    terragrunt_configs = _dedupe_rows(terragrunt_configs)
    relevant_provisioning_repositories = {
        repository
        for row in [*terraform_resources, *tf_modules]
        if (repository := str(row.get("repository") or "").strip())
    }
    if relevant_provisioning_repositories:
        terragrunt_configs = [
            row
            for row in terragrunt_configs
            if str(row.get("repository") or "").strip()
            in relevant_provisioning_repositories
        ]
    elif direct_only and not include_related_module_usage:
        terragrunt_configs = []
    provisioning_source_chains = group_provisioning_source_chains(
        terraform_modules=tf_modules_raw, terragrunt_configs=terragrunt_configs
    )
    deployment_chain = list(context.get("deployment_chain") or [])
    if direct_only:
        deployment_chain = _direct_deployment_chain_rows(deployment_chain)
    if max_depth is not None:
        deployment_chain = deployment_chain[:max_depth]

    limitations = list(context.get("limitations") or [])
    result = {
        "repository": dict(repo),
        "argocd_applications": argocd_apps,
        "argocd_applicationsets": argocd_appsets,
        "k8s_resources": k8s_resources,
        "crossplane_claims": claims,
        "terraform_resources": terraform_resources,
        "terraform_modules": tf_modules,
        "terragrunt_configs": terragrunt_configs,
        "provisioning_source_chains": provisioning_source_chains,
        "coverage": context.get("coverage"),
        "platforms": context.get("platforms", []),
        "deploys_from": context.get("deploys_from", []),
        "discovers_config_in": context.get("discovers_config_in", []),
        "provisioned_by": context.get("provisioned_by", []),
        "provisions_dependencies_for": context.get("provisions_dependencies_for", []),
        "deployment_chain": deployment_chain,
        "environments": context.get("environments", []),
        "observed_config_environments": context.get("observed_config_environments", []),
        "delivery_workflows": context.get("delivery_workflows", {}),
        "delivery_paths": context.get("delivery_paths", []),
        "controller_driven_paths": context.get("controller_driven_paths", []),
        "deployment_artifacts": context.get("deployment_artifacts", {}),
        "consumer_repositories": context.get("consumer_repositories", []),
        "api_surface": context.get("api_surface", {}),
        "hostnames": context.get("hostnames", []),
        "limitations": limitations,
        "trace_controls": {
            "direct_only": direct_only,
            "max_depth": max_depth,
            "include_related_module_usage": include_related_module_usage,
        },
    }
    trace_truncation = _trace_truncation(
        direct_only=direct_only,
        max_depth=max_depth,
        include_related_module_usage=include_related_module_usage,
    )
    if trace_truncation is not None:
        result["truncation"] = trace_truncation
    result["deployment_overview"] = build_deployment_overview(
        hostnames=result["hostnames"],
        api_surface=result["api_surface"],
        platforms=result["platforms"],
        delivery_paths=result["delivery_paths"],
        controller_driven_paths=result["controller_driven_paths"],
        provisioning_source_chains=(
            provisioning_source_chains if not direct_only else []
        ),
        k8s_resources=(k8s_resources if not direct_only else repo_k8s_resources),
        crossplane_claims=claims,
        terraform_resources=terraform_resources,
        terraform_modules=tf_modules if include_related_module_usage else [],
        deployment_artifacts=(
            result["deployment_artifacts"] if not direct_only else {}
        ),
        consumer_repositories=(
            result["consumer_repositories"] if not direct_only else []
        ),
    )
    documentation_evidence = collect_documentation_evidence(
        db_manager,
        repo_refs=[
            canonical_repository,
            *source_repositories,
            *list(context.get("deploys_from") or []),
            *list(context.get("discovers_config_in") or []),
            *list(context.get("provisioned_by") or []),
        ],
        subject_names=[canonical_name],
    )
    documentation_evidence["graph_context"] = build_graph_context_evidence(
        entrypoints=list(result.get("hostnames") or []),
        delivery_paths=list(result.get("delivery_paths") or []),
        deploys_from=list(result.get("deploys_from") or []),
        dependencies=list(result.get("consumer_repositories") or []),
        api_surface=dict(result.get("api_surface") or {}),
    )
    result["gitops_overview"] = build_gitops_overview(
        deploys_from=list(result.get("deploys_from") or []),
        discovers_config_in=list(result.get("discovers_config_in") or []),
        provisioned_by=list(result.get("provisioned_by") or []),
        delivery_paths=list(result.get("delivery_paths") or []),
        controller_driven_paths=list(result.get("controller_driven_paths") or []),
        deployment_artifacts=dict(result.get("deployment_artifacts") or {}),
        environments=list(result.get("environments") or []),
        observed_config_environments=list(
            result.get("observed_config_environments") or []
        ),
    )
    result["documentation_overview"] = build_documentation_overview(
        subject_name=canonical_name,
        subject_type="repository",
        repositories=[canonical_repository, *source_repositories],
        entrypoints=list(result.get("hostnames") or []),
        dependencies=list(result.get("consumer_repositories") or []),
        code_overview=None,
        gitops_overview=result.get("gitops_overview"),
        documentation_evidence=documentation_evidence,
        drilldowns={
            "repo_context": {"repo_id": canonical_repository.get("id")},
            "deployment_chain": {"service_name": canonical_name},
        },
    )
    result["support_overview"] = build_support_overview(
        subject_name=canonical_name,
        instances=[],
        repositories=[canonical_repository, *source_repositories],
        entrypoints=list(result.get("hostnames") or []),
        cloud_resources=[],
        shared_resources=[],
        dependencies=list(result.get("consumer_repositories") or []),
        gitops_overview=result.get("gitops_overview"),
        documentation_overview=result.get("documentation_overview"),
    )
    note_parts = [
        note
        for note in [
            _focused_trace_note(
                direct_only=direct_only,
                max_depth=max_depth,
                include_related_module_usage=include_related_module_usage,
            ),
            repo_summary_note(
                limitations=limitations,
                coverage=context.get("coverage"),
                environments=result["environments"],
                observed_config_environments=result["observed_config_environments"],
            ),
        ]
        if note
    ]
    if note_parts:
        result["note"] = " ".join(note_parts)
    if limitations:
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
    story = build_story_lines(
        deployment_overview=result["deployment_overview"],
        note=result.get("note", ""),
    )
    if story:
        result["story"] = story
    return portable_story_value(result)
