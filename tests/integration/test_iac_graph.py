"""Integration tests verifying IaC parsers produce correct graph nodes/edges.

Requires docker compose up (ingests ecosystems/ fixtures into Neo4j).

Run with:
    NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=testpassword \
    DATABASE_TYPE=neo4j uv run python -m pytest tests/integration/test_iac_graph.py -v
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="NEO4J_URI not set — start Neo4j with docker compose up -d",
)


class TestTerraformGraph:
    """Verify terraform_comprehensive repo produces correct graph."""

    def test_terraform_resources_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (r:TerraformResource) "
                "WHERE r.path CONTAINS 'terraform_comprehensive' "
                "RETURN count(r) as cnt"
            ).single()
            assert result["cnt"] >= 5

    def test_terraform_variables_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (v:TerraformVariable) "
                "WHERE v.path CONTAINS 'terraform_comprehensive' "
                "RETURN count(v) as cnt"
            ).single()
            assert result["cnt"] >= 5

    def test_terraform_variables_have_types(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            results = s.run(
                "MATCH (v:TerraformVariable) "
                "WHERE v.path CONTAINS 'terraform_comprehensive' "
                "RETURN v.name as name, v.var_type as var_type"
            ).data()
            types = {r["name"]: r["var_type"] for r in results}
            assert "aws_region" in types
            assert types["aws_region"] == "string"

    def test_terraform_outputs_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (o:TerraformOutput) "
                "WHERE o.path CONTAINS 'terraform_comprehensive' "
                "RETURN count(o) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_terraform_modules_with_source(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            results = s.run(
                "MATCH (m:TerraformModule) "
                "WHERE m.path CONTAINS 'terraform_comprehensive' "
                "RETURN m.name as name, m.source as source"
            ).data()
            assert len(results) >= 2
            names = [r["name"] for r in results]
            assert "vpc" in names

    def test_terraform_data_sources(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (ds:TerraformDataSource) "
                "WHERE ds.path CONTAINS 'terraform_comprehensive' "
                "RETURN count(ds) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_terraform_providers_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (p:TerraformProvider) "
                "WHERE p.path CONTAINS 'terraform_comprehensive' "
                "RETURN count(p) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_terraform_locals_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (l:TerraformLocal) "
                "WHERE l.path CONTAINS 'terraform_comprehensive' "
                "RETURN count(l) as cnt"
            ).single()
            assert result["cnt"] >= 2


class TestTerragruntGraph:
    """Verify terragrunt_comprehensive repo produces correct graph."""

    def test_terragrunt_configs_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (tg:TerragruntConfig) "
                "WHERE tg.path CONTAINS 'terragrunt_comprehensive' "
                "RETURN count(tg) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_terragrunt_has_terraform_source(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            results = s.run(
                "MATCH (tg:TerragruntConfig) "
                "WHERE tg.path CONTAINS 'terragrunt_comprehensive' "
                "AND tg.terraform_source IS NOT NULL "
                "RETURN tg.terraform_source as source"
            ).data()
            assert len(results) >= 1

    def test_terragrunt_persists_inputs_metadata(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (tg:TerragruntConfig) "
                "WHERE tg.path CONTAINS 'terragrunt_comprehensive/modules/eks' "
                "RETURN tg.inputs as inputs, tg.includes as includes"
            ).single()
            assert result is not None
            assert "cluster_name" in result["inputs"]
            assert "root" in result["includes"]


class TestHelmGraph:
    """Verify helm_comprehensive repo produces correct graph."""

    def test_helm_chart_indexed(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (h:HelmChart) "
                "WHERE h.path CONTAINS 'helm_comprehensive' "
                "RETURN count(h) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_helm_chart_has_properties(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (h:HelmChart) "
                "WHERE h.path CONTAINS 'helm_comprehensive' "
                "RETURN h.name as name, h.version as version"
            ).single()
            assert result is not None
            assert result["name"] == "comprehensive-app"

    def test_helm_values_indexed(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (hv:HelmValues) "
                "WHERE hv.path CONTAINS 'helm_comprehensive' "
                "RETURN count(hv) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_values_configures_chart(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (hv:HelmValues)-[:CONFIGURES]->(hc:HelmChart) "
                "WHERE hc.path CONTAINS 'helm_comprehensive' "
                "RETURN count(*) as cnt"
            ).single()
            assert result["cnt"] >= 1


class TestKustomizeGraph:
    """Verify kustomize_comprehensive repo produces correct graph."""

    def test_kustomize_overlays_indexed(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (ko:KustomizeOverlay) "
                "WHERE ko.path CONTAINS 'kustomize_comprehensive' "
                "RETURN count(ko) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_kustomize_k8s_resources(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (k:K8sResource) "
                "WHERE k.path CONTAINS 'kustomize_comprehensive' "
                "RETURN count(k) as cnt"
            ).single()
            assert result["cnt"] >= 2


class TestArgoCDGraph:
    """Verify argocd_comprehensive repo produces correct graph."""

    def test_argocd_applications_indexed(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (a:ArgoCDApplication) "
                "WHERE a.path CONTAINS 'argocd_comprehensive' "
                "RETURN count(a) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_argocd_applicationsets_indexed(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (as:ArgoCDApplicationSet) "
                "WHERE as.path CONTAINS 'argocd_comprehensive' "
                "RETURN count(as) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_argocd_app_has_source(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (a:ArgoCDApplication) "
                "WHERE a.path CONTAINS 'argocd_comprehensive' "
                "AND a.source_repo IS NOT NULL "
                "RETURN a.name as name"
            ).single()
            assert result is not None


class TestCrossplaneGraph:
    """Verify crossplane_comprehensive repo produces correct graph."""

    def test_crossplane_xrd_indexed(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (x:CrossplaneXRD) "
                "WHERE x.path CONTAINS 'crossplane_comprehensive' "
                "RETURN count(x) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_crossplane_composition_indexed(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:CrossplaneComposition) "
                "WHERE c.path CONTAINS 'crossplane_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_crossplane_claim_indexed(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:CrossplaneClaim) "
                "WHERE c.path CONTAINS 'crossplane_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_xrd_to_composition_chain(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (x:CrossplaneXRD)-[:IMPLEMENTED_BY]->(c:CrossplaneComposition) "
                "WHERE x.path CONTAINS 'crossplane_comprehensive' "
                "RETURN count(*) as cnt"
            ).single()
            assert result["cnt"] >= 1


class TestKubernetesGraph:
    """Verify kubernetes_comprehensive repo produces correct graph."""

    def test_all_resource_kinds(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            results = s.run(
                "MATCH (k:K8sResource) "
                "WHERE k.path CONTAINS 'kubernetes_comprehensive' "
                "RETURN DISTINCT k.kind as kind"
            ).data()
            kinds = {r["kind"] for r in results}
            expected = {
                "Deployment",
                "Service",
                "StatefulSet",
                "DaemonSet",
                "CronJob",
                "ConfigMap",
                "Secret",
                "Ingress",
                "HTTPRoute",
                "ServiceAccount",
            }
            assert kinds >= expected, f"Missing kinds: {expected - kinds}"

    def test_deployment_has_container_images(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (k:K8sResource {kind: 'Deployment'}) "
                "WHERE k.path CONTAINS 'kubernetes_comprehensive' "
                "RETURN k.container_images as ci"
            ).single()
            assert result is not None
            assert "myorg/comprehensive-api" in result["ci"]

    def test_service_selects_deployment(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (svc:K8sResource {kind: 'Service'})"
                "-[:SELECTS]->"
                "(deploy:K8sResource {kind: 'Deployment'}) "
                "WHERE svc.path CONTAINS 'kubernetes_comprehensive' "
                "RETURN svc.name as svc, deploy.name as deploy"
            ).single()
            assert result is not None

    def test_httproute_routes_to_service(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (r:K8sResource {kind: 'HTTPRoute'})"
                "-[:ROUTES_TO]->"
                "(svc:K8sResource {kind: 'Service'}) "
                "WHERE r.path CONTAINS 'kubernetes_comprehensive' "
                "RETURN r.name as route, svc.name as svc"
            ).single()
            assert result is not None

    def test_rbac_resources(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            results = s.run(
                "MATCH (k:K8sResource) "
                "WHERE k.path CONTAINS 'kubernetes_comprehensive' "
                "AND k.kind IN ['Role', 'ClusterRole', 'RoleBinding', 'ClusterRoleBinding'] "
                "RETURN k.kind as kind"
            ).data()
            assert len(results) >= 3


class TestCloudFormationGraph:
    """Verify cloudformation_comprehensive repo produces correct graph."""

    def test_cloudformation_resources_indexed(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (r:CloudFormationResource) "
                "WHERE r.path CONTAINS 'cloudformation_comprehensive' "
                "RETURN count(r) as cnt"
            ).single()
            assert result["cnt"] >= 5

    def test_cloudformation_resource_types(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            results = s.run(
                "MATCH (r:CloudFormationResource) "
                "WHERE r.path CONTAINS 'cloudformation_comprehensive' "
                "RETURN DISTINCT r.resource_type as type"
            ).data()
            types = {r["type"] for r in results}
            assert "AWS::S3::Bucket" in types
            assert "AWS::IAM::Role" in types

    def test_cloudformation_parameters_indexed(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (p:CloudFormationParameter) "
                "WHERE p.path CONTAINS 'cloudformation_comprehensive' "
                "RETURN count(p) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_cloudformation_outputs_indexed(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (o:CloudFormationOutput) "
                "WHERE o.path CONTAINS 'cloudformation_comprehensive' "
                "RETURN count(o) as cnt"
            ).single()
            assert result["cnt"] >= 2
