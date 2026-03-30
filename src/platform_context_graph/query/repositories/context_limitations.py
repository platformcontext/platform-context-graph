"""Repository-context limitation helpers."""

from __future__ import annotations

from typing import Any


def build_context_limitations(
    *,
    base_limitations: list[str],
    coverage: dict[str, Any] | None,
    entry_points: list[dict[str, Any]],
    infrastructure: dict[str, Any],
    deployment_chain: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
) -> list[str]:
    """Extend relationship limitations with repo-context truthfulness signals."""

    limitations: list[str] = []
    for code in base_limitations:
        if code not in limitations:
            limitations.append(code)

    if coverage is not None and coverage.get("completeness_state") != "complete":
        return limitations

    deployable = looks_like_deployable_repository(
        base_limitations=limitations,
        entry_points=entry_points,
        infrastructure=infrastructure,
        deployment_chain=deployment_chain,
        platforms=platforms,
    )
    if not deployable:
        return limitations

    if not platforms and "runtime_platform_unknown" not in limitations:
        limitations.append("runtime_platform_unknown")
    if not deployment_chain and "deployment_chain_incomplete" not in limitations:
        limitations.append("deployment_chain_incomplete")
    if not has_dns_evidence(infrastructure) and "dns_unknown" not in limitations:
        limitations.append("dns_unknown")
    if not entry_points and "entrypoint_unknown" not in limitations:
        limitations.append("entrypoint_unknown")
    return limitations


def looks_like_deployable_repository(
    *,
    base_limitations: list[str],
    entry_points: list[dict[str, Any]],
    infrastructure: dict[str, Any],
    deployment_chain: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
) -> bool:
    """Return whether the repo has enough runtime/deployment evidence to score gaps."""

    if entry_points or deployment_chain or platforms:
        return True
    if "runtime_platform_unknown" in base_limitations:
        return True
    if "deployment_chain_incomplete" in base_limitations:
        return True
    relevant_keys = {
        "argocd_applications",
        "argocd_applicationsets",
        "helm_charts",
        "helm_values",
        "k8s_resources",
        "kustomize_overlays",
        "provisioned_platforms",
        "runtime_platforms",
        "terragrunt_configs",
        "terraform_modules",
        "terraform_resources",
    }
    return any(infrastructure.get(key) for key in relevant_keys)


def has_dns_evidence(infrastructure: dict[str, Any]) -> bool:
    """Return whether repo context includes concrete DNS or routing evidence."""

    for resource in infrastructure.get("k8s_resources", []):
        if str(resource.get("kind") or "").lower() in {
            "certificate",
            "gateway",
            "httproute",
            "ingress",
            "ingressroute",
            "route",
            "virtualservice",
        }:
            return True
    for resource in infrastructure.get("terraform_resources", []):
        if str(resource.get("resource_type") or "").lower() in {
            # AWS
            "aws_alb",
            "aws_api_gateway_rest_api",
            "aws_apigatewayv2_api",
            "aws_cloudfront_distribution",
            "aws_lb",
            "aws_lb_listener",
            "aws_lb_listener_rule",
            "aws_route53_record",
            "aws_service_discovery_private_dns_namespace",
            "aws_service_discovery_public_dns_namespace",
            "aws_service_discovery_service",
            # Azure
            "azurerm_application_gateway",
            "azurerm_cdn_frontdoor_route",
            "azurerm_dns_a_record",
            "azurerm_dns_cname_record",
            "azurerm_dns_zone",
            "azurerm_frontdoor",
            "azurerm_traffic_manager_profile",
            # Cloudflare
            "cloudflare_dns_record",
            "cloudflare_load_balancer",
            "cloudflare_page_rule",
            "cloudflare_record",
            "cloudflare_tunnel",
            "cloudflare_workers_route",
            "cloudflare_zone",
            # GCP
            "google_cloud_run_domain_mapping",
            "google_compute_global_address",
            "google_compute_global_forwarding_rule",
            "google_compute_url_map",
            "google_dns_managed_zone",
            "google_dns_record_set",
        }:
            return True
    return False
