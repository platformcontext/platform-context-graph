"""Tests for infrastructure relationship linking during indexing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from platform_context_graph.relationships.infra_links import create_all_infra_links


class TestInfraLinkingDetection:
    """Test that create_all_infra_links correctly detects infra nodes."""

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
        builder = SimpleNamespace(db_manager=MagicMock())

        all_file_data = [
            self._make_file_data(
                k8s_resources=[],
                argocd_applications=[],
            ),
        ]

        create_all_infra_links(builder, all_file_data, info_logger_fn=lambda *_args: None)
        mock_linker_cls.assert_not_called()

    @patch("platform_context_graph.relationships.cross_repo_linker.CrossRepoLinker")
    def test_runs_when_infra_nodes_present(self, mock_linker_cls):
        """Linking runs when all_file_data contains infra items."""
        builder = SimpleNamespace(db_manager=MagicMock())

        mock_instance = MagicMock()
        mock_instance.link_all.return_value = {"SELECTS": 2}
        mock_linker_cls.return_value = mock_instance

        all_file_data = [
            self._make_file_data(
                k8s_resources=[{"name": "svc", "kind": "Service"}],
            ),
        ]

        create_all_infra_links(builder, all_file_data, info_logger_fn=lambda *_args: None)
        mock_linker_cls.assert_called_once_with(builder.db_manager)
        mock_instance.link_all.assert_called_once()
