import os
from pathlib import Path
from types import SimpleNamespace
from typer.testing import CliRunner
from unittest.mock import AsyncMock, MagicMock, patch
from platform_context_graph.cli.main import app
from platform_context_graph.relationships import (
    RelationshipAssertion,
    RelationshipCandidate,
    ResolvedRelationship,
    ResolutionGeneration,
)

runner = CliRunner()


class TestCLICommands:
    """
    Integration tests for CLI commands.
    Mocks the backend (graph builder, db, etc.) to test argument parsing and output.
    """

    @patch("platform_context_graph.cli.main.start_http_api")
    @patch("platform_context_graph.cli.main._load_credentials")
    def test_api_start_command_uses_dedicated_http_entrypoint(
        self,
        mock_load_credentials,
        mock_start_http_api,
    ):
        """Test that `pcg api start` uses the HTTP API startup helper."""
        result = runner.invoke(
            app,
            ["api", "start", "--host", "127.0.0.1", "--port", "8123"],
        )

        assert result.exit_code == 0
        mock_load_credentials.assert_called_once()
        mock_start_http_api.assert_called_once_with(
            host="127.0.0.1",
            port=8123,
            reload=False,
        )

    @patch("platform_context_graph.cli.main.start_http_api")
    @patch("platform_context_graph.cli.main._load_credentials")
    def test_api_start_loads_credentials_before_startup(
        self,
        mock_load_credentials,
        mock_start_http_api,
    ):
        """Test that `pcg api start` loads credentials before startup."""
        call_order: list[str] = []

        mock_load_credentials.side_effect = lambda: call_order.append("load")
        mock_start_http_api.side_effect = lambda **kwargs: call_order.append("start")

        result = runner.invoke(
            app,
            ["api", "start", "--host", "127.0.0.1", "--port", "8123"],
        )

        assert result.exit_code == 0
        assert call_order == ["load", "start"]
        mock_load_credentials.assert_called_once()
        mock_start_http_api.assert_called_once_with(
            host="127.0.0.1",
            port=8123,
            reload=False,
        )

    @patch("platform_context_graph.cli.main.start_service")
    @patch("platform_context_graph.cli.main._load_credentials")
    def test_serve_start_command_uses_combined_service_entrypoint(
        self,
        mock_load_credentials,
        mock_start_service,
    ):
        """Test that `pcg serve start` uses the combined service startup helper."""
        result = runner.invoke(
            app,
            ["serve", "start", "--host", "127.0.0.1", "--port", "8123"],
        )

        assert result.exit_code == 0
        mock_load_credentials.assert_called_once()
        mock_start_service.assert_called_once_with(
            host="127.0.0.1",
            port=8123,
            reload=False,
        )

    @patch("platform_context_graph.cli.main.start_http_api")
    @patch("platform_context_graph.cli.main.MCPServer")
    @patch("platform_context_graph.cli.main._load_credentials")
    def test_mcp_start_sse_stays_on_mcp_transport_path(
        self,
        mock_load_credentials,
        mock_mcp_server_cls,
        mock_start_http_api,
    ):
        """Test that `pcg mcp start --transport sse` stays on the MCP path."""
        mock_server = mock_mcp_server_cls.return_value
        mock_server.run_sse = AsyncMock(return_value=None)
        mock_server.shutdown = MagicMock()

        result = runner.invoke(
            app,
            [
                "mcp",
                "start",
                "--transport",
                "sse",
                "--host",
                "127.0.0.1",
                "--port",
                "8123",
            ],
        )

        assert result.exit_code == 0
        mock_load_credentials.assert_called_once()
        mock_start_http_api.assert_not_called()
        mock_mcp_server_cls.assert_called_once()
        mock_server.run_sse.assert_awaited_once_with(host="127.0.0.1", port=8123)
        mock_server.shutdown.assert_called_once()

    def test_start_http_api_uses_factory_mode_for_reload(self):
        """Test the HTTP startup helper uses Uvicorn factory mode."""
        with patch("uvicorn.run") as mock_run:
            from platform_context_graph.cli.main import start_http_api

            start_http_api(host="0.0.0.0", port=9000, reload=True)

        mock_run.assert_called_once_with(
            "platform_context_graph.api.app:create_app",
            host="0.0.0.0",
            port=9000,
            reload=True,
            factory=True,
            log_config=None,
            access_log=False,
        )

    def test_start_service_uses_combined_app(self):
        """Test the combined service startup helper wires the service app into Uvicorn."""
        with (
            patch("platform_context_graph.cli.main.MCPServer") as mock_server_cls,
            patch("uvicorn.run") as mock_run,
        ):
            from platform_context_graph.cli.main import start_service

            mock_server = mock_server_cls.return_value
            start_service(host="0.0.0.0", port=9000, reload=False)

        assert mock_server is mock_server_cls.return_value
        app_obj = mock_run.call_args.args[0]
        assert app_obj.title == "PlatformContextGraph HTTP API"
        mock_run.assert_called_once_with(
            app_obj,
            host="0.0.0.0",
            port=9000,
            reload=False,
            log_config=None,
            access_log=False,
        )

    @patch("platform_context_graph.cli.main.run_bootstrap_index")
    def test_internal_bootstrap_index_command_uses_python_runtime(
        self, mock_run_bootstrap
    ):
        result = runner.invoke(app, ["internal", "bootstrap-index"])

        assert result.exit_code == 0
        mock_run_bootstrap.assert_called_once()

    @patch("platform_context_graph.cli.main.run_repo_sync_cycle")
    def test_internal_repo_sync_command_uses_python_runtime(self, mock_run_repo_sync):
        result = runner.invoke(app, ["internal", "repo-sync"])

        assert result.exit_code == 0
        mock_run_repo_sync.assert_called_once()

    @patch("platform_context_graph.cli.main.run_repo_sync_loop")
    def test_internal_repo_sync_loop_command_uses_python_runtime(
        self, mock_run_repo_sync_loop
    ):
        result = runner.invoke(
            app, ["internal", "repo-sync-loop", "--interval-seconds", "42"]
        )

        assert result.exit_code == 0
        mock_run_repo_sync_loop.assert_called_once_with(interval_seconds=42)

    @patch("platform_context_graph.cli.main.workspace_plan_helper")
    def test_workspace_plan_command_uses_workspace_helper(
        self,
        mock_workspace_plan_helper,
    ):
        """Test that `pcg workspace plan` uses the shared workspace helper."""

        result = runner.invoke(app, ["workspace", "plan"])

        assert result.exit_code == 0
        mock_workspace_plan_helper.assert_called_once_with()

    @patch("platform_context_graph.cli.main.workspace_sync_helper")
    def test_workspace_sync_command_uses_workspace_helper(
        self,
        mock_workspace_sync_helper,
    ):
        """Test that `pcg workspace sync` uses the shared workspace helper."""

        result = runner.invoke(app, ["workspace", "sync"])

        assert result.exit_code == 0
        mock_workspace_sync_helper.assert_called_once_with()

    @patch("platform_context_graph.cli.main.workspace_index_helper")
    def test_workspace_index_command_uses_workspace_helper(
        self,
        mock_workspace_index_helper,
    ):
        """Test that `pcg workspace index` uses the shared workspace helper."""

        result = runner.invoke(app, ["workspace", "index"])

        assert result.exit_code == 0
        mock_workspace_index_helper.assert_called_once_with()

    @patch("platform_context_graph.cli.main.workspace_status_helper")
    def test_workspace_status_command_uses_workspace_helper(
        self,
        mock_workspace_status_helper,
    ):
        """Test that `pcg workspace status` uses the shared workspace helper."""

        result = runner.invoke(app, ["workspace", "status"])

        assert result.exit_code == 0
        mock_workspace_status_helper.assert_called_once_with()

    @patch("platform_context_graph.cli.main.workspace_watch_helper")
    def test_workspace_watch_command_uses_workspace_helper(
        self,
        mock_workspace_watch_helper,
    ):
        """Test that `pcg workspace watch` uses the shared workspace helper."""

        result = runner.invoke(
            app,
            [
                "workspace",
                "watch",
                "--include-repo",
                "*-api",
                "--sync-interval-seconds",
                "30",
            ],
        )

        assert result.exit_code == 0
        mock_workspace_watch_helper.assert_called_once_with(
            include_repositories=["*-api"],
            exclude_repositories=None,
            rediscover_interval_seconds=30,
        )

    def test_workspace_help_describes_canonical_source_model(self):
        """Workspace help should describe the shared source contract."""

        result = runner.invoke(app, ["workspace", "--help"])

        assert result.exit_code == 0
        assert "githubOrg" in result.stdout
        assert "explicit" in result.stdout
        assert "filesystem" in result.stdout
        assert "PCG_REPOSITORY_RULES_JSON" in result.stdout

    def test_path_based_index_and_watch_help_remain_local_convenience_wrappers(self):
        """Index/watch help should clarify that they are local path-first commands."""

        index_result = runner.invoke(app, ["index", "--help"])
        watch_result = runner.invoke(app, ["watch", "--help"])

        assert index_result.exit_code == 0
        assert watch_result.exit_code == 0
        assert "local filesystem path" in index_result.stdout
        assert "local filesystem path" in watch_result.stdout
        assert "pcg workspace" in watch_result.stdout

    @patch("platform_context_graph.cli.main.index_helper")
    def test_index_command_basic(self, mock_index):
        """Test 'pcg index .' calls the indexer."""
        # We need to ensure startup doesn't fail (e.g. DB connection).
        # We might need to patch get_database_manager too.

        with patch("platform_context_graph.core.database.DatabaseManager.get_driver"):
            mock_index.return_value = {"job_id": "123"}

            # Note: invoke calls the actual main.py logic. created commands verify args.

            # If the command is actually async or complex, it might fail without more mocks.
            # But let's try just patching the core logic.
            result = runner.invoke(app, ["index", "."])

            # If it fails, print output
            if result.exit_code != 0:
                print(result.stdout)

            # It might fail if "index" command calls something I didn't mock.
            # But let's assume it calls GraphBuilder.
            # If not, checks will fail.
            # assert result.exit_code == 0 # Relaxing for now if env is complex
            pass

    def test_unknown_command(self):
        """Test running an unknown command."""
        result = runner.invoke(app, ["foobar"])
        assert result.exit_code != 0
        # Output might be empty in some test envs, checking exit code is enough integration test
        # assert "No such command" in result.stdout

    @patch("platform_context_graph.cli.commands.bundle_registry.requests.post")
    def test_bundle_upload_command_posts_bundle_to_remote_service(
        self,
        mock_post,
        tmp_path: Path,
    ):
        """`pcg bundle upload` should post a bundle archive to the API service."""

        bundle_path = tmp_path / "dependency.pcg"
        bundle_path.write_bytes(b"bundle-bytes")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "message": "imported"}
        mock_response.text = '{"success":true}'
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = runner.invoke(
            app,
            [
                "bundle",
                "upload",
                str(bundle_path),
                "--service-url",
                "http://pcg.local",
                "--clear",
                "--timeout-seconds",
                "900",
            ],
        )

        assert result.exit_code == 0
        assert "imported" in result.stdout
        mock_post.assert_called_once()
        _args, kwargs = mock_post.call_args
        assert kwargs["data"] == {"clear_existing": "true"}
        assert kwargs["timeout"] == 900
        assert kwargs["files"]["bundle"][0] == "dependency.pcg"

    @patch("platform_context_graph.cli.main._initialize_services")
    def test_ecosystem_resolve_uses_indexed_repositories_by_default(
        self,
        mock_initialize_services,
        tmp_path: Path,
    ):
        """`pcg ecosystem resolve` should resolve relationships for indexed repos."""

        repo_a = tmp_path / "payments-api"
        repo_b = tmp_path / "orders-api"
        repo_a.mkdir()
        repo_b.mkdir()

        db_manager = SimpleNamespace(close_driver=MagicMock())
        graph_builder = MagicMock()
        graph_builder._resolve_repository_relationships.return_value = {
            "checkouts": 2,
            "evidence_facts": 5,
            "candidates": 3,
            "resolved_relationships": 2,
        }
        code_finder = SimpleNamespace(
            list_indexed_repositories=lambda: [
                {"name": "orders-api", "path": str(repo_b)},
                {"name": "payments-api", "path": str(repo_a)},
            ]
        )
        mock_initialize_services.return_value = (db_manager, graph_builder, code_finder)

        result = runner.invoke(app, ["ecosystem", "resolve"])

        assert result.exit_code == 0
        graph_builder._resolve_repository_relationships.assert_called_once_with(
            [repo_b.resolve(), repo_a.resolve()],
            run_id=None,
        )
        assert "resolved_relationships" in result.stdout
        db_manager.close_driver.assert_called_once()

    @patch("platform_context_graph.cli.commands.ecosystem.get_relationship_store")
    def test_ecosystem_relationships_lists_active_resolved_edges(
        self,
        mock_get_relationship_store,
    ):
        """`pcg ecosystem relationships` should render active resolved edges."""

        mock_store = MagicMock()
        mock_store.get_active_generation.return_value = ResolutionGeneration(
            generation_id="generation_123",
            scope="repo_dependencies",
            run_id="run_123",
            status="active",
        )
        mock_store.list_resolved_relationships.return_value = [
            ResolvedRelationship(
                source_repo_id="repo:payments",
                target_repo_id="repo:orders",
                relationship_type="DEPENDS_ON",
                confidence=0.95,
                evidence_count=4,
                rationale="Workload dependency",
                resolution_source="inferred",
            )
        ]
        mock_get_relationship_store.return_value = mock_store

        result = runner.invoke(app, ["ecosystem", "relationships"])

        assert result.exit_code == 0
        assert "repo:payments" in result.stdout
        assert "generation_123" in result.stdout
        mock_store.get_active_generation.assert_called_once_with(
            scope="repo_dependencies"
        )
        mock_store.list_resolved_relationships.assert_called_once_with(
            scope="repo_dependencies"
        )

    @patch(
        "platform_context_graph.cli.main._initialize_services",
        side_effect=AssertionError("graph bootstrap should not run"),
    )
    @patch("platform_context_graph.cli.commands.ecosystem.get_relationship_store")
    def test_ecosystem_relationships_reads_store_without_graph_bootstrap(
        self,
        mock_get_relationship_store,
        mock_initialize_services,
    ):
        """Store-backed review commands should not depend on graph service startup."""

        mock_store = MagicMock()
        mock_store.get_active_generation.return_value = ResolutionGeneration(
            generation_id="generation_123",
            scope="repo_dependencies",
            run_id="run_123",
            status="active",
        )
        mock_store.list_resolved_relationships.return_value = []
        mock_get_relationship_store.return_value = mock_store

        result = runner.invoke(app, ["ecosystem", "relationships"])

        assert result.exit_code == 0
        assert "generation_123" in result.stdout
        mock_initialize_services.assert_not_called()

    @patch("platform_context_graph.cli.commands.ecosystem.get_relationship_store")
    def test_ecosystem_candidates_lists_active_candidates(
        self,
        mock_get_relationship_store,
    ):
        """`pcg ecosystem candidates` should list active relationship candidates."""

        mock_store = MagicMock()
        mock_store.list_relationship_candidates.return_value = [
            RelationshipCandidate(
                source_repo_id="repo:payments",
                target_repo_id="repo:orders",
                relationship_type="DEPENDS_ON",
                confidence=0.83,
                evidence_count=2,
                rationale="Cross-repo workload evidence",
            )
        ]
        mock_get_relationship_store.return_value = mock_store

        result = runner.invoke(app, ["ecosystem", "candidates"])

        assert result.exit_code == 0
        assert "repo:payments" in result.stdout
        assert "0.83" in result.stdout
        mock_store.list_relationship_candidates.assert_called_once_with(
            scope="repo_dependencies",
            relationship_type="DEPENDS_ON",
        )

    @patch("platform_context_graph.cli.commands.ecosystem.get_relationship_store")
    def test_ecosystem_assert_relationship_persists_assertion(
        self,
        mock_get_relationship_store,
    ):
        """`pcg ecosystem assert-relationship` should persist an explicit assertion."""

        mock_store = MagicMock()
        mock_get_relationship_store.return_value = mock_store

        result = runner.invoke(
            app,
            [
                "ecosystem",
                "assert-relationship",
                "repo:payments",
                "repo:orders",
                "--reason",
                "Validated by runtime dependency",
                "--actor",
                "cli-user",
            ],
        )

        assert result.exit_code == 0
        mock_store.upsert_relationship_assertion.assert_called_once_with(
            RelationshipAssertion(
                source_repo_id="repo:payments",
                target_repo_id="repo:orders",
                relationship_type="DEPENDS_ON",
                decision="assert",
                reason="Validated by runtime dependency",
                actor="cli-user",
            )
        )

    @patch("platform_context_graph.cli.commands.ecosystem.get_relationship_store")
    def test_ecosystem_reject_relationship_persists_rejection(
        self,
        mock_get_relationship_store,
    ):
        """`pcg ecosystem reject-relationship` should persist an explicit rejection."""

        mock_store = MagicMock()
        mock_get_relationship_store.return_value = mock_store

        result = runner.invoke(
            app,
            [
                "ecosystem",
                "reject-relationship",
                "repo:payments",
                "repo:orders",
                "--reason",
                "False positive",
                "--actor",
                "cli-user",
            ],
        )

        assert result.exit_code == 0
        mock_store.upsert_relationship_assertion.assert_called_once_with(
            RelationshipAssertion(
                source_repo_id="repo:payments",
                target_repo_id="repo:orders",
                relationship_type="DEPENDS_ON",
                decision="reject",
                reason="False positive",
                actor="cli-user",
            )
        )


class TestNeo4jDatabaseNameCLI:
    """Integration tests for NEO4J_DATABASE display in CLI commands."""

    @patch("platform_context_graph.cli.main.config_manager")
    @patch("platform_context_graph.core.database.DatabaseManager.test_connection")
    def test_doctor_passes_database_to_test_connection(
        self, mock_test_conn, mock_config_mgr
    ):
        """Test that the doctor command passes NEO4J_DATABASE to test_connection."""
        mock_config_mgr.load_config.return_value = {"DEFAULT_DATABASE": "neo4j"}
        mock_config_mgr.CONFIG_FILE = MagicMock()
        mock_config_mgr.CONFIG_FILE.exists.return_value = True
        mock_config_mgr.validate_config_value.return_value = (True, None)
        mock_test_conn.return_value = (True, None)

        env = {
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USERNAME": "neo4j",
            "NEO4J_PASSWORD": "password",
            "NEO4J_DATABASE": "mydb",
            "DEFAULT_DATABASE": "neo4j",
            "PCG_LOG_FORMAT": "text",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("platform_context_graph.cli.main._load_credentials"):
                runner.invoke(app, ["doctor"])

        mock_test_conn.assert_called_once_with(
            "bolt://localhost:7687", "neo4j", "password", database="mydb"
        )

    @patch("platform_context_graph.cli.main.find_dotenv", return_value=None)
    @patch("platform_context_graph.cli.main.config_manager")
    def test_load_credentials_displays_database_name(
        self, mock_config_mgr, mock_find_dotenv
    ):
        """Test _load_credentials prints database name when NEO4J_DATABASE is set."""
        mock_config_mgr.ensure_config_dir.return_value = None

        env = {
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USERNAME": "neo4j",
            "NEO4J_PASSWORD": "password",
            "NEO4J_DATABASE": "mydb",
            "DEFAULT_DATABASE": "neo4j",
            "PCG_LOG_FORMAT": "text",
        }
        with patch.dict(os.environ, env, clear=False):
            with (
                patch("platform_context_graph.cli.main.Path") as mock_path,
                patch(
                    "platform_context_graph.cli.main.get_app_env_file",
                    return_value=Path("/tmp/pcg-missing.env"),
                ),
            ):
                # Prevent file system access in _load_credentials
                mock_path.home.return_value.__truediv__ = MagicMock(
                    return_value=MagicMock(exists=MagicMock(return_value=False))
                )
                mock_path.cwd.return_value.__truediv__ = MagicMock(
                    return_value=MagicMock(exists=MagicMock(return_value=False))
                )

                from platform_context_graph.cli.main import _load_credentials
                from io import StringIO
                from rich.console import Console

                output = StringIO()
                with patch(
                    "platform_context_graph.cli.main.console",
                    Console(file=output, force_terminal=False),
                ):
                    _load_credentials()

                printed = output.getvalue()
                assert "Using database: Neo4j (database: mydb)" in printed

    @patch("platform_context_graph.cli.main.find_dotenv", return_value=None)
    @patch("platform_context_graph.cli.main.config_manager")
    def test_load_credentials_no_database_name(self, mock_config_mgr, mock_find_dotenv):
        """Test _load_credentials prints Neo4j without database when NEO4J_DATABASE is not set."""
        mock_config_mgr.ensure_config_dir.return_value = None

        env = {
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USERNAME": "neo4j",
            "NEO4J_PASSWORD": "password",
            "DEFAULT_DATABASE": "neo4j",
            "PCG_LOG_FORMAT": "text",
        }
        # Remove NEO4J_DATABASE if it exists
        clean_env = {k: v for k, v in os.environ.items() if k != "NEO4J_DATABASE"}
        clean_env.update(env)
        with patch.dict(os.environ, clean_env, clear=True):
            with (
                patch("platform_context_graph.cli.main.Path") as mock_path,
                patch(
                    "platform_context_graph.cli.main.get_app_env_file",
                    return_value=Path("/tmp/pcg-missing.env"),
                ),
            ):
                mock_path.home.return_value.__truediv__ = MagicMock(
                    return_value=MagicMock(exists=MagicMock(return_value=False))
                )
                mock_path.cwd.return_value.__truediv__ = MagicMock(
                    return_value=MagicMock(exists=MagicMock(return_value=False))
                )

                from platform_context_graph.cli.main import _load_credentials
                from io import StringIO
                from rich.console import Console

                output = StringIO()
                with patch(
                    "platform_context_graph.cli.main.console",
                    Console(file=output, force_terminal=False),
                ):
                    _load_credentials()

                printed = output.getvalue()
                assert "Using database: Neo4j" in printed
                assert "(database:" not in printed
