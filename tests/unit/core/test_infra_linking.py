"""Tests for infrastructure relationship linking during indexing."""

import pytest
from unittest.mock import MagicMock, patch

from platform_context_graph.tools.languages.yaml_infra import InfraYAMLParser


class TestContainerImageExtraction:
    """Test container image extraction from K8s workload specs."""

    @pytest.fixture()
    def parser(self):
        return InfraYAMLParser("yaml")

    def test_deployment_extracts_container_images(self, parser, tmp_path):
        yaml_content = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: default
spec:
  template:
    spec:
      containers:
        - name: app
          image: myorg/my-app:v1.0
        - name: sidecar
          image: envoyproxy/envoy:latest
"""
        f = tmp_path / "deployment.yaml"
        f.write_text(yaml_content)
        result = parser.parse(str(f))
        assert len(result["k8s_resources"]) == 1
        resource = result["k8s_resources"][0]
        assert resource["container_images"] == (
            "myorg/my-app:v1.0,envoyproxy/envoy:latest"
        )

    def test_statefulset_extracts_container_images(self, parser, tmp_path):
        yaml_content = """\
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: my-db
  namespace: default
spec:
  template:
    spec:
      containers:
        - name: db
          image: postgres:15
"""
        f = tmp_path / "statefulset.yaml"
        f.write_text(yaml_content)
        result = parser.parse(str(f))
        assert result["k8s_resources"][0]["container_images"] == "postgres:15"

    def test_daemonset_extracts_container_images(self, parser, tmp_path):
        yaml_content = """\
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: log-agent
  namespace: kube-system
spec:
  template:
    spec:
      containers:
        - name: agent
          image: fluent/fluentd:v1.16
"""
        f = tmp_path / "daemonset.yaml"
        f.write_text(yaml_content)
        result = parser.parse(str(f))
        assert result["k8s_resources"][0]["container_images"] == "fluent/fluentd:v1.16"

    def test_job_extracts_container_images(self, parser, tmp_path):
        yaml_content = """\
apiVersion: batch/v1
kind: Job
metadata:
  name: migration
  namespace: default
spec:
  template:
    spec:
      containers:
        - name: migrate
          image: myorg/migrator:latest
"""
        f = tmp_path / "job.yaml"
        f.write_text(yaml_content)
        result = parser.parse(str(f))
        assert result["k8s_resources"][0]["container_images"] == "myorg/migrator:latest"

    def test_cronjob_extracts_container_images(self, parser, tmp_path):
        yaml_content = """\
apiVersion: batch/v1
kind: CronJob
metadata:
  name: backup
  namespace: default
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: myorg/backup-tool:v2
"""
        f = tmp_path / "cronjob.yaml"
        f.write_text(yaml_content)
        result = parser.parse(str(f))
        assert result["k8s_resources"][0]["container_images"] == "myorg/backup-tool:v2"

    def test_init_containers_also_extracted(self, parser, tmp_path):
        yaml_content = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: with-init
  namespace: default
spec:
  template:
    spec:
      initContainers:
        - name: init
          image: busybox:1.36
      containers:
        - name: app
          image: myorg/app:v1
"""
        f = tmp_path / "deployment.yaml"
        f.write_text(yaml_content)
        result = parser.parse(str(f))
        assert (
            result["k8s_resources"][0]["container_images"]
            == "myorg/app:v1,busybox:1.36"
        )

    def test_service_has_no_container_images(self, parser, tmp_path):
        yaml_content = """\
apiVersion: v1
kind: Service
metadata:
  name: my-svc
  namespace: default
spec:
  selector:
    app: my-app
"""
        f = tmp_path / "service.yaml"
        f.write_text(yaml_content)
        result = parser.parse(str(f))
        assert "container_images" not in result["k8s_resources"][0]

    def test_deployment_no_containers_no_images(self, parser, tmp_path):
        yaml_content = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: empty
  namespace: default
spec:
  template:
    spec:
      containers: []
"""
        f = tmp_path / "deployment.yaml"
        f.write_text(yaml_content)
        result = parser.parse(str(f))
        assert "container_images" not in result["k8s_resources"][0]


class TestInfraLinkingDetection:
    """Test that _create_all_infra_links correctly detects infra nodes."""

    def _make_file_data(self, **kwargs):
        """Create a minimal file_data dict with given infra items."""
        base = {
            "path": "/tmp/test.yaml",
            "lang": "yaml",
            "functions": [],
            "classes": [],
            "imports": [],
        }
        base.update(kwargs)
        return base

    @patch("platform_context_graph.relationships.cross_repo_linker.CrossRepoLinker")
    def test_skips_when_no_infra_nodes(self, mock_linker_cls):
        """Linking is skipped when all_file_data has no infra items."""
        from platform_context_graph.tools.graph_builder import GraphBuilder

        gb = MagicMock(spec=GraphBuilder)
        gb.db_manager = MagicMock()

        all_file_data = [
            self._make_file_data(
                k8s_resources=[],
                argocd_applications=[],
            ),
        ]

        GraphBuilder._create_all_infra_links(gb, all_file_data)
        mock_linker_cls.assert_not_called()

    @patch("platform_context_graph.relationships.cross_repo_linker.CrossRepoLinker")
    def test_runs_when_infra_nodes_present(self, mock_linker_cls):
        """Linking runs when all_file_data contains infra items."""
        from platform_context_graph.tools.graph_builder import GraphBuilder

        gb = MagicMock(spec=GraphBuilder)
        gb.db_manager = MagicMock()

        mock_instance = MagicMock()
        mock_instance.link_all.return_value = {"SELECTS": 2}
        mock_linker_cls.return_value = mock_instance

        all_file_data = [
            self._make_file_data(
                k8s_resources=[{"name": "svc", "kind": "Service"}],
            ),
        ]

        GraphBuilder._create_all_infra_links(gb, all_file_data)
        mock_linker_cls.assert_called_once_with(gb.db_manager)
        mock_instance.link_all.assert_called_once()
