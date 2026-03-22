"""Tests for YAML infrastructure parser."""

import importlib
from pathlib import Path

import pytest

from platform_context_graph.tools.languages.yaml_infra import InfraYAMLParser


class TestInfraYAMLParser:
    """Test the YAML infrastructure parser."""

    @pytest.fixture(scope="class")
    def parser(self):
        """Build the YAML infrastructure parser under test."""
        return InfraYAMLParser("yaml")

    @pytest.fixture(scope="class")
    def yaml_fixtures(self, sample_projects_path):
        """Return the YAML infrastructure sample project fixture path."""
        path = sample_projects_path / "sample_project_yaml_infra"
        if not path.exists():
            pytest.fail(f"YAML infra sample project not found at {path}")
        return path

    # --- ArgoCD Application ---

    def test_parse_argocd_application(self, parser, yaml_fixtures):
        """Parse an ArgoCD Application manifest."""
        result = parser.parse(str(yaml_fixtures / "argocd" / "application.yaml"))

        assert "argocd_applications" in result
        apps = result["argocd_applications"]
        assert len(apps) == 1

        app = apps[0]
        assert app["name"] == "iac-eks-addons"
        assert app["line_number"] == 1
        assert app["namespace"] == "argocd"
        assert app["project"] == "platform"
        assert app["source_repo"] == "https://github.com/myorg/iac-eks-argocd.git"
        assert app["source_path"] == "overlays/production/addons/cert-manager"
        assert app["dest_server"] == "https://kubernetes.default.svc"
        assert app["dest_namespace"] == "cert-manager"

    def test_parse_argocd_applicationset(self, parser, yaml_fixtures):
        """Parse an ArgoCD ApplicationSet manifest."""
        result = parser.parse(str(yaml_fixtures / "argocd" / "applicationset.yaml"))

        assert "argocd_applicationsets" in result
        appsets = result["argocd_applicationsets"]
        assert len(appsets) == 1

        appset = appsets[0]
        assert appset["name"] == "cluster-addons"
        assert appset["namespace"] == "argocd"
        assert "generators" in appset
        assert appset["project"] == "platform"
        assert appset["source_repos"] == "https://github.com/myorg/iac-eks-argocd.git"
        assert appset["source_paths"] == "overlays/*/addons/*"
        assert appset["source_roots"] == "overlays/"

    def test_parse_argocd_applicationset_matrix_generator_collects_nested_git_sources(
        self, parser, tmp_path
    ):
        """Parse nested matrix generators and normalize workload roots."""
        application_set = tmp_path / "applicationset.yaml"
        application_set.write_text(
            """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: api-node-search
  namespace: argocd
spec:
  generators:
    - matrix:
        generators:
          - git:
              repoURL: https://github.com/boatsgroup/helm-charts
              files:
                - path: argocd/api-node-search/overlays/*/config.yaml
  template:
    spec:
      project: "{{.argocd.project}}"
      sources:
        - repoURL: "{{.git.repoURL}}"
          path: argocd/api-node-search/overlays/{{.environment}}
      destination:
        namespace: "{{.helm.namespace}}"
"""
        )

        result = parser.parse(str(application_set))

        appset = result["argocd_applicationsets"][0]
        assert (
            appset["source_repos"] == "https://github.com/boatsgroup/helm-charts"
        )
        assert (
            appset["source_paths"]
            == "argocd/api-node-search/overlays/*/config.yaml,argocd/api-node-search/overlays/{{.environment}}"
        )
        assert appset["source_roots"] == "argocd/api-node-search/"

    # --- Crossplane ---

    def test_parse_crossplane_xrd(self, parser, yaml_fixtures):
        """Parse a Crossplane CompositeResourceDefinition."""
        result = parser.parse(str(yaml_fixtures / "crossplane" / "xrd.yaml"))

        assert "crossplane_xrds" in result
        xrds = result["crossplane_xrds"]
        assert len(xrds) == 1

        xrd = xrds[0]
        assert xrd["name"] == "xiamroles.iam.aws.myorg.io"
        assert xrd["group"] == "iam.aws.myorg.io"
        assert xrd["kind"] == "XIAMRole"
        assert xrd["claim_kind"] == "IAMRole"

    def test_parse_crossplane_composition(self, parser, yaml_fixtures):
        """Parse a Crossplane Composition."""
        result = parser.parse(str(yaml_fixtures / "crossplane" / "composition.yaml"))

        assert "crossplane_compositions" in result
        comps = result["crossplane_compositions"]
        assert len(comps) == 1

        comp = comps[0]
        assert comp["name"] == "iam-role-composition"
        assert comp["composite_kind"] == "XIAMRole"
        assert comp["composite_api_version"] == "iam.aws.myorg.io/v1alpha1"

    def test_parse_crossplane_claim(self, parser, yaml_fixtures):
        """Parse a Crossplane Claim."""
        result = parser.parse(str(yaml_fixtures / "crossplane" / "claim.yaml"))

        assert "crossplane_claims" in result
        claims = result["crossplane_claims"]
        assert len(claims) == 1

        claim = claims[0]
        assert claim["name"] == "my-service-role"
        assert claim["kind"] == "IAMRole"
        assert claim["api_version"] == "iam.aws.myorg.crossplane.io/v1alpha1"
        assert claim["namespace"] == "default"

    # --- K8s Resources ---

    def test_parse_k8s_multi_document(self, parser, yaml_fixtures):
        """Parse a multi-document YAML with K8s resources."""
        result = parser.parse(str(yaml_fixtures / "k8s" / "deployment.yaml"))

        assert "k8s_resources" in result
        resources = result["k8s_resources"]
        assert len(resources) == 3

        kinds = [r["kind"] for r in resources]
        assert "Deployment" in kinds
        assert "Service" in kinds
        assert "ServiceAccount" in kinds

        deployment = next(r for r in resources if r["kind"] == "Deployment")
        assert deployment["name"] == "my-api"
        assert deployment["namespace"] == "production"

        sa = next(r for r in resources if r["kind"] == "ServiceAccount")
        assert sa["name"] == "my-api-sa"
        assert "annotations" in sa

    def test_parse_k8s_httproute(self, parser, yaml_fixtures):
        """Parse a Gateway API HTTPRoute."""
        result = parser.parse(str(yaml_fixtures / "k8s" / "httproute.yaml"))

        assert "k8s_resources" in result
        resources = result["k8s_resources"]
        assert len(resources) == 1
        assert resources[0]["kind"] == "HTTPRoute"
        assert resources[0]["name"] == "my-api-route"

    # --- Kustomize ---

    def test_parse_kustomization(self, parser, yaml_fixtures):
        """Parse a kustomization.yaml file."""
        result = parser.parse(str(yaml_fixtures / "kustomize" / "kustomization.yaml"))

        assert "kustomize_overlays" in result
        overlays = result["kustomize_overlays"]
        assert len(overlays) == 1

        overlay = overlays[0]
        assert overlay["name"] == "kustomization"
        assert overlay["namespace"] == "production"
        assert "../base" in overlay["resources"]

    # --- Helm ---

    def test_parse_helm_chart(self, parser, yaml_fixtures):
        """Parse a Chart.yaml file."""
        result = parser.parse(str(yaml_fixtures / "helm" / "Chart.yaml"))

        assert "helm_charts" in result
        charts = result["helm_charts"]
        assert len(charts) == 1

        chart = charts[0]
        assert chart["name"] == "my-api-chart"
        assert chart["version"] == "0.1.0"
        assert chart["app_version"] == "1.0.0"

    def test_parse_helm_values(self, parser, yaml_fixtures):
        """Parse a values.yaml file."""
        result = parser.parse(str(yaml_fixtures / "helm" / "values.yaml"))

        assert "helm_values" in result
        values = result["helm_values"]
        assert len(values) == 1

        val = values[0]
        assert val["name"] == "values"

    # --- Edge Cases ---

    def test_parse_empty_yaml(self, parser, temp_test_dir):
        """Parse an empty YAML file gracefully."""
        f = temp_test_dir / "empty.yaml"
        f.write_text("")

        result = parser.parse(str(f))
        assert result["path"] == str(f)

    def test_parse_non_k8s_yaml(self, parser, temp_test_dir):
        """Parse a YAML that is not K8s/infra (e.g., CI config)."""
        f = temp_test_dir / "ci.yaml"
        f.write_text(
            "name: CI\non:\n  push:\n    branches: [main]\n"
            "jobs:\n  build:\n    runs-on: ubuntu-latest\n"
        )

        result = parser.parse(str(f))
        # Should not produce any infra resources
        total = sum(
            len(result.get(k, []))
            for k in [
                "k8s_resources",
                "argocd_applications",
                "crossplane_xrds",
            ]
        )
        assert total == 0

    def test_parse_invalid_yaml(self, parser, temp_test_dir):
        """Parse an invalid YAML file without crashing."""
        f = temp_test_dir / "bad.yaml"
        f.write_text("key: [invalid\nyaml: {broken")

        result = parser.parse(str(f))
        assert result["path"] == str(f)

    def test_parse_yaml_with_ansible_vault_tag(self, parser, temp_test_dir):
        """Unknown tags like ``!vault`` should not drop otherwise valid manifests."""

        f = temp_test_dir / "vault-configmap.yaml"
        f.write_text(
            "apiVersion: v1\n"
            "kind: ConfigMap\n"
            "metadata:\n"
            "  name: sample-config\n"
            "data:\n"
            "  secret: !vault |\n"
            "    $ANSIBLE_VAULT;1.1;AES256\n"
            "    6137616263646566\n"
        )

        result = parser.parse(str(f))

        assert len(result["k8s_resources"]) == 1
        assert result["k8s_resources"][0]["name"] == "sample-config"

    def test_parse_yaml_with_tabs_after_colons(self, parser, temp_test_dir):
        """Tab-separated values should retry with a whitespace-normalized fallback."""

        f = temp_test_dir / "tabbed-openapi.yaml"
        f.write_text(
            "apiVersion: v1\n"
            "kind: ConfigMap\n"
            "metadata:\n"
            "  name: sample-openapi\n"
            "data:\n"
            "  spec: |\n"
            "    openapi: 3.0.0\n"
            "    example:\tavailable-coop-brokerage\n"
        )

        result = parser.parse(str(f))

        assert len(result["k8s_resources"]) == 1
        assert result["k8s_resources"][0]["name"] == "sample-openapi"

    def test_result_structure_has_required_keys(self, parser, yaml_fixtures):
        """Verify all result dicts have the standard keys."""
        result = parser.parse(str(yaml_fixtures / "argocd" / "application.yaml"))

        # Must have path and lang
        assert result["path"] == str(yaml_fixtures / "argocd" / "application.yaml")
        assert result["lang"] == "yaml"
        assert "is_dependency" in result

    def test_parser_returns_line_numbers(self, parser, yaml_fixtures):
        """Verify parsed items include line_number."""
        result = parser.parse(str(yaml_fixtures / "k8s" / "deployment.yaml"))

        for resource in result["k8s_resources"]:
            assert "line_number" in resource
            assert isinstance(resource["line_number"], int)
            assert resource["line_number"] >= 1

    def test_no_k8s_standalone_resources_without_api_version(
        self, parser, temp_test_dir
    ):
        """YAML with no apiVersion should not produce K8s nodes."""
        f = temp_test_dir / "plain.yaml"
        f.write_text("database:\n  host: localhost\n  port: 5432\n")

        result = parser.parse(str(f))
        assert len(result.get("k8s_resources", [])) == 0

    def test_custom_domain_claim_indexed_as_k8s_resource(self, parser, temp_test_dir):
        """Claims with non-crossplane.io domains are K8s resources.

        Crossplane claims using custom XRD groups (e.g.,
        iam.aws.myorg.io) don't match *.crossplane.io and
        are indexed as generic K8sResource nodes. The
        cross-repo linker matches them to XRDs later.
        """
        f = temp_test_dir / "custom-claim.yaml"
        f.write_text(
            "apiVersion: iam.aws.myorg.io/v1alpha1\n"
            "kind: IAMRole\n"
            "metadata:\n"
            "  name: my-role\n"
            "  namespace: default\n"
            "spec:\n"
            "  roleName: test\n"
        )

        result = parser.parse(str(f))
        # Not detected as crossplane claim (custom domain)
        assert len(result.get("crossplane_claims", [])) == 0
        # But is a valid K8s resource
        assert len(result.get("k8s_resources", [])) == 1
        assert result["k8s_resources"][0]["kind"] == "IAMRole"


def test_yaml_infra_facade_stays_thin_and_semantic_modules_are_importable() -> None:
    """Keep the YAML facade small and its semantic parser modules importable."""
    languages_dir = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "platform_context_graph"
        / "tools"
        / "languages"
    )
    yaml_facade = languages_dir / "yaml_infra.py"

    assert len(yaml_facade.read_text(encoding="utf-8").splitlines()) <= 200

    for module_name in (
        "argocd",
        "crossplane",
        "helm",
        "kubernetes_manifest",
        "kustomize",
    ):
        module = importlib.import_module(
            f"platform_context_graph.tools.languages.{module_name}"
        )
        assert module is not None
