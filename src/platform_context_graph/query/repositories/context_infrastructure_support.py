"""Infrastructure query configuration for repository context assembly."""

from __future__ import annotations


def infrastructure_label_queries() -> dict[str, tuple[str, str]]:
    """Return repository infrastructure label queries keyed by payload section."""

    return {
        "k8s_resources": (
            "K8sResource",
            """
            RETURN n.name as name, n.kind as kind,
                   n.namespace as namespace,
                   f.relative_path as file
            """,
        ),
        "terraform_resources": (
            "TerraformResource",
            """
            RETURN n.name as name,
                   n.resource_type as resource_type,
                   f.relative_path as file
            """,
        ),
        "terraform_modules": (
            "TerraformModule",
            """
            RETURN n.name as name,
                   n.source as source,
                   n.version as version,
                   n.deployment_name as deployment_name,
                   n.repo_name as repo_name,
                   n.create_deploy as create_deploy,
                   n.cluster_name as cluster_name,
                   n.zone_id as zone_id,
                   n.deploy_entry_point as deploy_entry_point
            """,
        ),
        "terraform_variables": (
            "TerraformVariable",
            """
            RETURN n.name as name,
                   n.description as description,
                   n[$default_key] as default
            """,
        ),
        "terraform_outputs": (
            "TerraformOutput",
            """
            RETURN n.name as name,
                   n.description as description
            """,
        ),
        "cloudformation_resources": (
            "CloudFormationResource",
            """
            RETURN n.name as name,
                   n.resource_type as resource_type,
                   f.relative_path as file
            """,
        ),
        "cloudformation_parameters": (
            "CloudFormationParameter",
            """
            RETURN n.name as name,
                   n.type as type,
                   f.relative_path as file
            """,
        ),
        "cloudformation_outputs": (
            "CloudFormationOutput",
            """
            RETURN n.name as name,
                   n.description as description,
                   n[$export_name_key] as export_name,
                   f.relative_path as file
            """,
        ),
        "argocd_applications": (
            "ArgoCDApplication",
            """
            RETURN n.name as name, n[$project_key] as project,
                   n[$dest_namespace_key] as dest_namespace,
                   n[$source_repo_key] as source_repo
            """,
        ),
        "argocd_applicationsets": (
            "ArgoCDApplicationSet",
            """
            RETURN n.name as name,
                   n[$generators_key] as generators,
                   n[$project_key] as project,
                   n[$dest_namespace_key] as dest_namespace,
                   n[$source_repos_key] as source_repos,
                   n[$source_paths_key] as source_paths
            """,
        ),
        "crossplane_xrds": (
            "CrossplaneXRD",
            """
            RETURN n.name as name, n.kind as kind,
                   n[$claim_kind_key] as claim_kind
            """,
        ),
        "crossplane_compositions": (
            "CrossplaneComposition",
            """
            RETURN n.name as name,
                   n[$composite_kind_key] as composite_kind
            """,
        ),
        "crossplane_claims": (
            "CrossplaneClaim",
            """
            RETURN n.name as name, n.kind as kind,
                   n.namespace as namespace
            """,
        ),
        "helm_charts": (
            "HelmChart",
            """
            RETURN n.name as name, n.version as version,
                   n.app_version as app_version
            """,
        ),
        "helm_values": (
            "HelmValues",
            """
            RETURN n.name as name,
                   n.top_level_keys as top_level_keys
            """,
        ),
        "kustomize_overlays": (
            "KustomizeOverlay",
            """
            RETURN n.name as name, n.namespace as namespace,
                   n.resources as resources
            """,
        ),
        "terragrunt_configs": (
            "TerragruntConfig",
            """
            RETURN n.name as name,
                   n[$terraform_source_key] as terraform_source
            """,
        ),
    }


def infrastructure_query_kwargs() -> dict[str, str]:
    """Return dynamic property keys shared by infrastructure queries."""

    return {
        "claim_kind_key": "claim_kind",
        "composite_kind_key": "composite_kind",
        "default_key": "default",
        "dest_namespace_key": "dest_namespace",
        "export_name_key": "export_name",
        "generators_key": "generators",
        "project_key": "project",
        "source_paths_key": "source_paths",
        "source_repo_key": "source_repo",
        "source_repos_key": "source_repos",
        "terraform_source_key": "terraform_source",
    }


__all__ = ["infrastructure_label_queries", "infrastructure_query_kwargs"]
