"""Tests for infrastructure relationship linking during indexing."""

import pytest
from unittest.mock import MagicMock, patch


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
