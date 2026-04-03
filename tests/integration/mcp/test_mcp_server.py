import asyncio
import importlib
import io
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_MCP_ROOT = (
    Path(__file__).resolve().parents[3] / "src" / "platform_context_graph" / "mcp"
)
for module_name, module_path in [
    ("platform_context_graph.mcp", _MCP_ROOT),
    ("platform_context_graph.mcp.tools", _MCP_ROOT / "tools"),
    ("platform_context_graph.mcp.tools.handlers", _MCP_ROOT / "tools" / "handlers"),
]:
    if module_name not in sys.modules:
        module = ModuleType(module_name)
        module.__path__ = [str(module_path)]
        sys.modules[module_name] = module

from platform_context_graph.mcp.server import DEFAULT_EDIT_DISTANCE, MCPServer
from platform_context_graph.mcp.tool_registry import TOOLS
from platform_context_graph.query.context import ServiceAliasError
from platform_context_graph.repository_identity import canonical_repository_id

sys.modules["platform_context_graph.mcp"].MCPServer = MCPServer


class TestMCPServer:
    """
    Integration tests for the MCP Server.
    We mock the underlying DB and Logic handlers to verify the Server routes requests correctly.
    """

    @pytest.fixture
    def mock_server(self):
        with patch(
            "platform_context_graph.mcp.server.get_database_manager"
        ) as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            with (
                patch("platform_context_graph.mcp.server.JobManager"),
                patch("platform_context_graph.mcp.server.GraphBuilder"),
                patch("platform_context_graph.mcp.server.CodeFinder"),
                patch("platform_context_graph.mcp.server.CodeWatcher"),
            ):

                server = MCPServer()
                # Mock handle_tool_call to avoid needing to mock every handler import
                # BUT here we want to test handle_tool_call logic too?
                # Let's mock the internal handlers instead.

                return server

    def test_tool_routing(self, mock_server):
        """Test that handle_tool_call routes to the correct internal method."""

        async def run_test():
            # Mock specific handler wrapper
            mock_server.find_code_tool = MagicMock(return_value={"result": "found"})

            # Act
            result = await mock_server.handle_tool_call("find_code", {"query": "test"})

            # Assert
            mock_server.find_code_tool.assert_called_once_with(query="test")
            assert result == {"result": "found"}

        asyncio.run(run_test())

    def test_get_index_status_is_listed_and_callable(self, mock_server):
        """Runtime status tools advertised by MCP must also dispatch through tools/call."""

        async def run_test():
            mock_server.get_index_status_tool = MagicMock(
                return_value={"run_id": "run-123", "status": "running"}
            )

            result = await mock_server.handle_tool_call(
                "get_index_status", {"target": "/tmp/repos"}
            )

            mock_server.get_index_status_tool.assert_called_once_with(
                target="/tmp/repos"
            )
            assert result == {"run_id": "run-123", "status": "running"}

        asyncio.run(run_test())

    def test_unknown_tool(self, mock_server):
        """Test unknown tool returns error."""

        async def run_test():
            result = await mock_server.handle_tool_call("unknown_tool", {})
            assert "error" in result
            assert "Unknown tool" in result["error"]

        asyncio.run(run_test())

    def test_add_code_to_graph_routing(self, mock_server):
        """Verify routing for complex tools."""

        async def run_test():
            # Mock the handler function imported in server.py
            with patch(
                "platform_context_graph.mcp.server.indexing.add_code_to_graph"
            ) as mock_handler:
                mock_handler.return_value = {"job_id": "123"}
                mock_server.tools["add_code_to_graph"] = TOOLS["add_code_to_graph"]

                # The tool on the server instance simply calls this handler
                # We must ensure the arguments are passed correctly (including wrappers)

                result = await mock_server.handle_tool_call(
                    "add_code_to_graph", {"path": "."}
                )

                # We can't strictly assert called_once because arguments are complex (bound methods)
                # But we can check result
                assert result == {"job_id": "123"}

        asyncio.run(run_test())

    def test_jsonrpc_transport_logs_structured_request_and_tool_context(
        self, mock_server, monkeypatch
    ):
        """JSON-RPC transport logs should include stable event names and IDs."""

        async def run_test():
            observability = importlib.import_module(
                "platform_context_graph.observability"
            )
            observability.reset_observability_for_tests()
            monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
            monkeypatch.setenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT",
                "http://otel-collector.monitoring.svc.cluster.local:4317",
            )
            monkeypatch.setenv("ENABLE_APP_LOGS", "INFO")
            monkeypatch.setenv("PCG_LOG_FORMAT", "json")

            from opentelemetry.sdk.metrics.export import InMemoryMetricReader
            from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
                InMemorySpanExporter,
            )

            observability.configure_test_exporters(
                span_exporter=InMemorySpanExporter(),
                metric_reader=InMemoryMetricReader(),
            )
            buffer = io.StringIO()
            observability.configure_logging(
                component="mcp",
                runtime_role="mcp",
                stream=buffer,
            )

            mock_server.handle_tool_call = AsyncMock(return_value={"ok": True})
            mock_server._apply_repo_access_handoff = AsyncMock(
                side_effect=lambda payload, **_kwargs: payload
            )

            response, status_code = await mock_server._handle_jsonrpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": "rpc-42",
                    "method": "tools/call",
                    "params": {
                        "name": "get_index_status",
                        "arguments": {},
                    },
                },
                transport="jsonrpc-stdio",
            )

            assert status_code == 200
            assert response is not None

            records = [
                json.loads(line)
                for line in buffer.getvalue().splitlines()
                if line.strip()
            ]
            request_records = [
                record
                for record in records
                if record.get("event_name") == "mcp.request.received"
            ]
            tool_records = [
                record
                for record in records
                if record.get("event_name") == "mcp.tool.completed"
            ]
            assert request_records
            assert tool_records
            assert request_records[-1]["request_id"] == "rpc-42"
            assert request_records[-1]["correlation_id"] == "rpc-42"
            assert request_records[-1]["transport"] == "jsonrpc-stdio"
            assert request_records[-1]["extra_keys"]["jsonrpc_method"] == "tools/call"
            assert "transport" not in request_records[-1]["extra_keys"]
            assert tool_records[-1]["request_id"] == "rpc-42"
            assert tool_records[-1]["extra_keys"]["tool_name"] == "get_index_status"
            assert "transport" not in tool_records[-1]["extra_keys"]

        asyncio.run(run_test())

    def test_find_code_wrapper_routes_through_query_service(self, mock_server):
        with patch(
            "platform_context_graph.mcp.server.code_queries.search_code"
        ) as mock_search:
            mock_search.return_value = {"ranked_results": []}

            result = mock_server.find_code_tool(
                query="Payment_API",
                fuzzy_search=True,
                edit_distance=1,
                repo_path="/repo",
            )

        mock_search.assert_called_once_with(
            mock_server.code_finder,
            query="payment api",
            repo_id="/repo",
            scope="auto",
            exact=False,
            limit=15,
            edit_distance=1,
        )
        assert result == {
            "success": True,
            "query": "payment api",
            "results": {"ranked_results": []},
        }

    def test_find_code_wrapper_defaults_to_exact_symbol_search(self, mock_server):
        """The MCP search tool should default to exact symbol lookup."""

        with patch(
            "platform_context_graph.mcp.server.code_queries.search_code"
        ) as mock_search:
            mock_search.return_value = {"ranked_results": []}

            result = mock_server.find_code_tool(
                query="Payment_API",
                repo_id="repository:r_ab12cd34",
            )

        mock_search.assert_called_once_with(
            mock_server.code_finder,
            query="Payment_API",
            repo_id="repository:r_ab12cd34",
            scope="auto",
            exact=True,
            limit=10,
            edit_distance=None,
        )
        assert result == {
            "success": True,
            "query": "Payment_API",
            "results": {"ranked_results": []},
        }

    def test_find_code_wrapper_falls_back_to_default_limit_for_invalid_canonical_value(
        self, mock_server
    ):
        with patch(
            "platform_context_graph.mcp.server.code_queries.search_code"
        ) as mock_search:
            mock_search.return_value = {"ranked_results": []}

            result = mock_server.find_code_tool(
                query="Payment_API",
                repo_id="repository:r_ab12cd34",
                limit="not-a-number",
            )

        mock_search.assert_called_once_with(
            mock_server.code_finder,
            query="Payment_API",
            repo_id="repository:r_ab12cd34",
            scope="auto",
            exact=True,
            limit=10,
            edit_distance=None,
        )
        assert result["success"] is True

    def test_find_code_wrapper_falls_back_to_legacy_limit_for_invalid_fuzzy_value(
        self, mock_server
    ):
        with patch(
            "platform_context_graph.mcp.server.code_queries.search_code"
        ) as mock_search:
            mock_search.return_value = {"ranked_results": []}

            result = mock_server.find_code_tool(
                query="Payment_API",
                fuzzy_search=True,
                repo_path="/repo",
                limit=None,
            )

        mock_search.assert_called_once_with(
            mock_server.code_finder,
            query="payment api",
            repo_id="/repo",
            scope="auto",
            exact=False,
            limit=15,
            edit_distance=DEFAULT_EDIT_DISTANCE,
        )
        assert result["success"] is True

    def test_find_code_wrapper_returns_repo_identity_for_workspace_results(
        self, mock_server
    ):
        class FakeResult:
            def __init__(self, *, records=None):
                self._records = records or []

            def data(self):
                return self._records

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **_kwargs):
                if "MATCH (r:Repository)" in query:
                    return FakeResult(
                        records=[
                            {
                                "name": "payments-api",
                                "path": "/repos/payments-api",
                                "local_path": "/repos/payments-api",
                                "remote_url": "https://github.com/platformcontext/payments-api",
                                "repo_slug": "platformcontext/payments-api",
                                "has_remote": True,
                            }
                        ]
                    )
                raise AssertionError(f"unexpected query: {query}")

        mock_server.code_finder.find_related_code.return_value = {
            "ranked_results": [{"path": "/repos/payments-api/src/payments.py"}]
        }
        mock_server.code_finder.get_driver.return_value.session.return_value = (
            FakeSession()
        )

        result = mock_server.find_code_tool(query="payments", scope="workspace")

        assert result == {
            "success": True,
            "query": "payments",
            "results": {
                "ranked_results": [
                    {
                        "relative_path": "src/payments.py",
                        "repo_id": canonical_repository_id(
                            remote_url="https://github.com/platformcontext/payments-api",
                            local_path="/repos/payments-api",
                        ),
                        "repo_access": {
                            "state": "needs_local_checkout",
                            "repo_id": canonical_repository_id(
                                remote_url="https://github.com/platformcontext/payments-api",
                                local_path="/repos/payments-api",
                            ),
                            "repo_slug": "platformcontext/payments-api",
                            "remote_url": "https://github.com/platformcontext/payments-api",
                            "recommended_action": "ask_user_for_local_path",
                            "interaction_mode": "conversational",
                        },
                    }
                ]
            },
        }

    def test_relationship_wrapper_routes_through_query_service(self, mock_server):
        with patch(
            "platform_context_graph.mcp.server.code_queries.get_code_relationships"
        ) as mock_relationships:
            mock_relationships.return_value = {"results": []}

            result = mock_server.analyze_code_relationships_tool(
                query_type="find_callers",
                target="foo",
                context="src/foo.py",
                repo_path="/repo",
            )

        mock_relationships.assert_called_once_with(
            mock_server.code_finder,
            query_type="find_callers",
            target="foo",
            context="src/foo.py",
            repo_id="/repo",
            scope="auto",
        )
        assert result == {
            "success": True,
            "query_type": "find_callers",
            "target": "foo",
            "context": "src/foo.py",
            "results": {"results": []},
        }

    def test_find_dead_code_wrapper_prefers_repo_id_contract(self, mock_server):
        with patch(
            "platform_context_graph.mcp.server.code_queries.find_dead_code"
        ) as mock_dead_code:
            mock_dead_code.return_value = {"potentially_unused_functions": []}

            result = mock_server.find_dead_code_tool(
                repo_id="repository:r_ab12cd34",
                scope="repo",
                exclude_decorated_with=["@app.route"],
            )

        mock_dead_code.assert_called_once_with(
            mock_server.code_finder,
            repo_id="repository:r_ab12cd34",
            scope="repo",
            exclude_decorated_with=["@app.route"],
        )
        assert result == {
            "success": True,
            "query_type": "dead_code",
            "results": {"potentially_unused_functions": []},
        }

    def test_repo_and_infra_wrappers_route_through_query_services(self, mock_server):
        with (
            patch(
                "platform_context_graph.mcp.server.repository_queries.get_repository_stats"
            ) as mock_repo_stats,
            patch(
                "platform_context_graph.mcp.server.infra_queries.search_infra_resources"
            ) as mock_search_infra,
        ):
            mock_repo_stats.return_value = {"success": True, "stats": {"files": 3}}
            mock_search_infra.return_value = {
                "query": "rds",
                "category": "terraform",
                "results": {},
            }

            repo_result = mock_server.get_repository_stats_tool(
                repo_id="repository:r_ab12cd34"
            )
            infra_result = mock_server.find_infra_resources_tool(
                query="rds", category="terraform"
            )

        mock_repo_stats.assert_called_once_with(
            mock_server.code_finder, repo_id="repository:r_ab12cd34"
        )
        mock_search_infra.assert_called_once_with(
            mock_server.db_manager,
            query="rds",
            types=["terraform"],
            environment=None,
            limit=50,
        )
        assert repo_result == {"success": True, "stats": {"files": 3}}
        assert infra_result == {"query": "rds", "category": "terraform", "results": {}}

    def test_repository_wrappers_require_canonical_repo_ids(self, mock_server):
        """Repository MCP tools should use canonical repo IDs, not repo names or paths."""

        with (
            patch(
                "platform_context_graph.mcp.server.repository_queries.get_repository_context"
            ) as mock_repo_context,
            patch(
                "platform_context_graph.mcp.server.repository_queries.get_repository_stats"
            ) as mock_repo_stats,
            patch(
                "platform_context_graph.mcp.server.repository_queries.get_repository_coverage"
            ) as mock_repo_coverage,
            patch(
                "platform_context_graph.mcp.server.repository_queries.list_repository_coverage"
            ) as mock_list_repo_coverage,
        ):
            mock_repo_context.return_value = {
                "repository": {"id": "repository:r_ab12cd34"}
            }
            mock_repo_stats.return_value = {"success": True, "stats": {"files": 3}}
            mock_repo_coverage.return_value = {
                "run_id": "run-123",
                "repo_id": "repository:r_ab12cd34",
                "status": "completed",
            }
            mock_list_repo_coverage.return_value = {
                "run_id": "run-123",
                "repositories": [],
            }

            context_result = mock_server.get_repo_context_tool(
                repo_id="repository:r_ab12cd34"
            )
            stats_result = mock_server.get_repository_stats_tool(
                repo_id="repository:r_ab12cd34"
            )
            coverage_result = mock_server.get_repository_coverage_tool(
                repo_id="repository:r_ab12cd34",
                run_id="run-123",
            )
            coverage_list_result = mock_server.list_repository_coverage_tool(
                run_id="run-123",
                only_incomplete=True,
                statuses=["running"],
                limit=25,
            )

        mock_repo_context.assert_called_once_with(
            mock_server.db_manager,
            repo_id="repository:r_ab12cd34",
        )
        mock_repo_stats.assert_called_once_with(
            mock_server.code_finder,
            repo_id="repository:r_ab12cd34",
        )
        mock_repo_coverage.assert_called_once_with(
            mock_server.db_manager,
            repo_id="repository:r_ab12cd34",
            run_id="run-123",
        )
        mock_list_repo_coverage.assert_called_once_with(
            mock_server.db_manager,
            run_id="run-123",
            only_incomplete=True,
            statuses=["running"],
            limit=25,
        )
        assert context_result == {"repository": {"id": "repository:r_ab12cd34"}}
        assert stats_result == {"success": True, "stats": {"files": 3}}
        assert coverage_result["status"] == "completed"
        assert coverage_list_result == {"run_id": "run-123", "repositories": []}

    def test_context_wrappers_route_through_query_services(self, mock_server):
        with (
            patch(
                "platform_context_graph.mcp.server.entity_resolution_queries.resolve_entity"
            ) as mock_resolve,
            patch(
                "platform_context_graph.mcp.server.context_queries.get_entity_context"
            ) as mock_entity_context,
            patch(
                "platform_context_graph.mcp.server.context_queries.get_workload_context"
            ) as mock_workload_context,
            patch(
                "platform_context_graph.mcp.server.context_queries.get_service_context"
            ) as mock_service_context,
        ):
            mock_resolve.return_value = {"matches": []}
            workload_context = {
                "workload": {
                    "id": "workload:payments-api",
                    "type": "workload",
                    "kind": "service",
                    "name": "payments-api",
                },
                "instance": {
                    "id": "workload-instance:payments-api:prod",
                    "type": "workload_instance",
                    "kind": "service",
                    "name": "payments-api",
                    "environment": "prod",
                    "workload_id": "workload:payments-api",
                },
                "repositories": [],
                "cloud_resources": [],
                "shared_resources": [],
                "dependencies": [],
                "entrypoints": [],
                "evidence": [],
            }
            mock_entity_context.return_value = {
                "entity": workload_context["workload"],
                **workload_context,
            }
            mock_workload_context.return_value = workload_context
            mock_service_context.return_value = {
                **workload_context,
                "requested_as": "service",
            }

            resolve_result = mock_server.resolve_entity_tool(
                query="payments", types=["workload"]
            )
            entity_result = mock_server.get_entity_context_tool(
                entity_id="workload:payments-api",
                environment="prod",
            )
            workload_result = mock_server.get_workload_context_tool(
                workload_id="workload:payments-api",
                environment="prod",
            )
            service_result = mock_server.get_service_context_tool(
                workload_id="workload:payments-api",
                environment="prod",
            )

        mock_resolve.assert_called_once_with(
            mock_server.db_manager,
            query="payments",
            types=["workload"],
            kinds=None,
            environment=None,
            repo_id=None,
            exact=False,
            limit=10,
        )
        mock_entity_context.assert_called_once_with(
            mock_server.db_manager,
            entity_id="workload:payments-api",
            environment="prod",
        )
        mock_workload_context.assert_called_once_with(
            mock_server.db_manager,
            workload_id="workload:payments-api",
            environment="prod",
        )
        mock_service_context.assert_called_once_with(
            mock_server.db_manager,
            workload_id="workload:payments-api",
            environment="prod",
        )
        assert resolve_result == {"matches": []}
        assert entity_result == {
            "entity": workload_context["workload"],
            **workload_context,
        }
        assert workload_result == workload_context
        assert service_result == {
            **workload_context,
            "requested_as": "service",
        }

    def test_impact_and_compare_wrappers_route_through_query_services(
        self, mock_server
    ):
        with (
            patch(
                "platform_context_graph.mcp.server.impact_queries.trace_resource_to_code"
            ) as mock_trace,
            patch(
                "platform_context_graph.mcp.server.impact_queries.explain_dependency_path"
            ) as mock_path,
            patch(
                "platform_context_graph.mcp.server.impact_queries.find_change_surface"
            ) as mock_surface,
            patch(
                "platform_context_graph.mcp.server.compare_queries.compare_environments"
            ) as mock_compare,
        ):
            mock_trace.return_value = {"paths": []}
            mock_path.return_value = {"path": {}}
            mock_surface.return_value = {"impacted": []}
            mock_compare.return_value = {"changed": {"cloud_resources": []}}

            trace_result = mock_server.trace_resource_to_code_tool(
                start="cloud-resource:shared-payments-prod",
                environment="prod",
                max_depth=4,
            )
            path_result = mock_server.explain_dependency_path_tool(
                source="workload:payments-api",
                target="cloud-resource:shared-payments-prod",
                environment="prod",
            )
            surface_result = mock_server.find_change_surface_tool(
                target="terraform-module:shared-rds-module",
                environment="prod",
            )
            compare_result = mock_server.compare_environments_tool(
                workload_id="workload:payments-api",
                left="stage",
                right="prod",
            )

        mock_trace.assert_called_once_with(
            mock_server.db_manager,
            start="cloud-resource:shared-payments-prod",
            environment="prod",
            max_depth=4,
        )
        mock_path.assert_called_once_with(
            mock_server.db_manager,
            source="workload:payments-api",
            target="cloud-resource:shared-payments-prod",
            environment="prod",
        )
        mock_surface.assert_called_once_with(
            mock_server.db_manager,
            target="terraform-module:shared-rds-module",
            environment="prod",
        )
        mock_compare.assert_called_once_with(
            mock_server.db_manager,
            workload_id="workload:payments-api",
            left="stage",
            right="prod",
        )
        assert trace_result == {"paths": []}
        assert path_result == {"path": {}}
        assert surface_result == {"impacted": []}
        assert compare_result == {"changed": {"cloud_resources": []}}

    def test_compare_environments_tool_schema_requires_workload_id(self, mock_server):
        schema = TOOLS["compare_environments"]["inputSchema"]

        assert schema["required"] == ["workload_id", "left", "right"]
        assert "default" not in schema["properties"]["workload_id"]

    def test_service_context_wrapper_returns_structured_error_on_alias_rejection(
        self, mock_server
    ):
        with patch(
            "platform_context_graph.mcp.server.context_queries.get_service_context"
        ) as mock_service_context:
            mock_service_context.side_effect = ServiceAliasError(
                "Workload 'workload:ledger-worker' is not a service and cannot be addressed via service alias"
            )

            result = mock_server.get_service_context_tool(
                workload_id="workload:ledger-worker",
                environment="prod",
            )

        assert "error" in result
        assert "not a service" in result["error"]

    def test_jsonrpc_request_emits_mcp_spans_and_tool_metrics(
        self, mock_server, monkeypatch
    ):
        pytest.importorskip("opentelemetry.sdk")
        from opentelemetry.sdk.metrics.export import InMemoryMetricReader
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )
        import importlib

        observability = importlib.import_module("platform_context_graph.observability")
        observability.reset_observability_for_tests()
        monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
        monkeypatch.setenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://otel-collector.monitoring.svc.cluster.local:4317",
        )

        span_exporter = InMemorySpanExporter()
        metric_reader = InMemoryMetricReader()
        observability.initialize_observability(
            component="mcp",
            span_exporter=span_exporter,
            metric_reader=metric_reader,
        )

        async def run_test():
            with patch.object(
                mock_server, "handle_tool_call", AsyncMock(return_value={"ok": True})
            ):
                response, status = await mock_server._handle_jsonrpc_request(
                    {
                        "jsonrpc": "2.0",
                        "id": 7,
                        "method": "tools/call",
                        "params": {
                            "name": "find_code",
                            "arguments": {"query": "payments"},
                        },
                    }
                )
            assert status == 200
            assert response["id"] == 7

        asyncio.run(run_test())

        spans = span_exporter.get_finished_spans()
        span_names = [span.name for span in spans]
        assert "pcg.mcp.request" in span_names
        assert "pcg.mcp.tool" in span_names

        metric_points = []
        metrics_data = metric_reader.get_metrics_data()
        for resource_metric in metrics_data.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    for point in metric.data.data_points:
                        metric_points.append(
                            (
                                metric.name,
                                dict(point.attributes),
                                getattr(point, "value", None),
                            )
                        )

        assert any(
            metric_name == "pcg_mcp_requests_total"
            and attrs.get("pcg.jsonrpc.method") == "tools/call"
            and attrs.get("pcg.transport") == "jsonrpc-stdio"
            for metric_name, attrs, _value in metric_points
        )
        assert any(
            metric_name == "pcg_mcp_tool_calls_total"
            and attrs.get("pcg.tool.name") == "find_code"
            for metric_name, attrs, _value in metric_points
        )

    def test_initialize_tracks_client_elicitation_capability(self, mock_server):
        async def run_test():
            response, status = await mock_server._handle_jsonrpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "capabilities": {
                            "elicitation": {},
                        }
                    },
                }
            )

            assert status == 200
            assert response["result"]["capabilities"]["tools"]["listTools"] is True
            assert mock_server.client_capabilities.get("elicitation") == {}

        asyncio.run(run_test())

    def test_tools_call_marks_repo_access_for_elicitation_capable_clients(
        self, mock_server
    ):
        async def run_test():
            await mock_server._handle_jsonrpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"capabilities": {"elicitation": {}}},
                }
            )
            mock_server._client_request_handler = AsyncMock(
                return_value={
                    "action": "accept",
                    "content": {
                        "action": "use_local_checkout",
                        "local_path": "/Users/allen/repos/payments-api",
                    },
                }
            )

            with patch.object(
                mock_server,
                "handle_tool_call",
                AsyncMock(
                    return_value={
                        "results": [
                            {
                                "repo_access": {
                                    "state": "needs_local_checkout",
                                    "repo_id": "repository:r_ab12cd34",
                                    "repo_slug": "platformcontext/payments-api",
                                    "remote_url": "https://github.com/platformcontext/payments-api",
                                    "local_path": "/srv/repos/payments-api",
                                    "recommended_action": "ask_user_for_local_path",
                                }
                            }
                        ]
                    }
                ),
            ):
                response, status = await mock_server._handle_jsonrpc_request(
                    {
                        "jsonrpc": "2.0",
                        "id": 7,
                        "method": "tools/call",
                        "params": {
                            "name": "find_code",
                            "arguments": {"query": "payments"},
                        },
                    }
                )

            assert status == 200
            payload = json.loads(response["result"]["content"][0]["text"])
            repo_access = payload["results"][0]["repo_access"]
            assert repo_access["interaction_mode"] == "elicitation"
            assert repo_access["state"] == "available"
            assert repo_access["recommended_action"] == "use_local_checkout"
            assert repo_access["client_local_path"] == "/Users/allen/repos/payments-api"
            assert repo_access["user_response_action"] == "accept"
            mock_server._client_request_handler.assert_awaited_once()

        asyncio.run(run_test())

    def test_tools_call_defaults_repo_access_to_conversational_without_elicitation(
        self, mock_server
    ):
        async def run_test():
            with patch.object(
                mock_server,
                "handle_tool_call",
                AsyncMock(
                    return_value={
                        "results": [
                            {
                                "repo_access": {
                                    "state": "needs_local_checkout",
                                    "repo_id": "repository:r_ab12cd34",
                                    "repo_slug": "platformcontext/payments-api",
                                    "remote_url": "https://github.com/platformcontext/payments-api",
                                    "local_path": "/srv/repos/payments-api",
                                    "recommended_action": "ask_user_for_local_path",
                                }
                            }
                        ]
                    }
                ),
            ):
                response, status = await mock_server._handle_jsonrpc_request(
                    {
                        "jsonrpc": "2.0",
                        "id": 7,
                        "method": "tools/call",
                        "params": {
                            "name": "find_code",
                            "arguments": {"query": "payments"},
                        },
                    }
                )

            assert status == 200
            payload = json.loads(response["result"]["content"][0]["text"])
            repo_access = payload["results"][0]["repo_access"]
            assert repo_access["interaction_mode"] == "conversational"

        asyncio.run(run_test())

    def test_tools_call_uses_conversational_fallback_for_http_transport(
        self, mock_server
    ):
        async def run_test():
            await mock_server._handle_jsonrpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"capabilities": {"elicitation": {}}},
                },
                transport="jsonrpc-http",
            )
            mock_server._client_request_handler = AsyncMock(
                return_value={
                    "action": "accept",
                    "content": {
                        "action": "use_local_checkout",
                        "local_path": "/Users/allen/repos/payments-api",
                    },
                }
            )

            with patch.object(
                mock_server,
                "handle_tool_call",
                AsyncMock(
                    return_value={
                        "results": [
                            {
                                "repo_access": {
                                    "state": "needs_local_checkout",
                                    "repo_id": "repository:r_ab12cd34",
                                    "repo_slug": "platformcontext/payments-api",
                                    "remote_url": "https://github.com/platformcontext/payments-api",
                                    "local_path": "/srv/repos/payments-api",
                                    "recommended_action": "ask_user_for_local_path",
                                }
                            }
                        ]
                    }
                ),
            ):
                response, status = await mock_server._handle_jsonrpc_request(
                    {
                        "jsonrpc": "2.0",
                        "id": 7,
                        "method": "tools/call",
                        "params": {
                            "name": "find_code",
                            "arguments": {"query": "payments"},
                        },
                    },
                    transport="jsonrpc-http",
                )

            assert status == 200
            payload = json.loads(response["result"]["content"][0]["text"])
            repo_access = payload["results"][0]["repo_access"]
            assert repo_access["interaction_mode"] == "conversational"
            mock_server._client_request_handler.assert_not_awaited()

        asyncio.run(run_test())


class TestSSETransport:
    """Tests for the SSE HTTP transport exposed by run_sse()."""

    @pytest.fixture
    def sse_client(self):
        """Build a FastAPI TestClient around the SSE app without starting uvicorn."""
        pytest.importorskip("httpx")
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        from starlette.responses import Response
        from starlette.testclient import TestClient
        import json

        with patch(
            "platform_context_graph.mcp.server.get_database_manager"
        ) as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            with (
                patch("platform_context_graph.mcp.server.JobManager"),
                patch("platform_context_graph.mcp.server.GraphBuilder"),
                patch("platform_context_graph.mcp.server.CodeFinder"),
                patch("platform_context_graph.mcp.server.CodeWatcher"),
            ):

                server = MCPServer()

        # Build the same FastAPI app that run_sse() creates
        app = FastAPI()

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.post("/message")
        async def message(request: Request):
            try:
                body = await request.json()
            except (json.JSONDecodeError, ValueError):
                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    },
                )
            response, status_code = await server._handle_jsonrpc_request(body)
            if response is None:
                return Response(status_code=204)
            return JSONResponse(content=response, status_code=status_code)

        return TestClient(app)

    def test_sse_health(self, sse_client):
        """GET /health returns 200 + status ok."""
        resp = sse_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_sse_initialize(self, sse_client):
        """POST /message with initialize returns server info."""
        resp = sse_client.post(
            "/message", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["result"]["serverInfo"]["name"] == "PlatformContextGraph"

    def test_sse_tools_list(self, sse_client):
        """POST /message with tools/list returns tools."""
        resp = sse_client.post(
            "/message", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data["result"]
        assert isinstance(data["result"]["tools"], list)

    def test_sse_notification_returns_204(self, sse_client):
        """POST /message with a notification (no id) returns 204."""
        resp = sse_client.post(
            "/message", json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        assert resp.status_code == 204
        assert resp.content == b""

    def test_sse_malformed_json_returns_400(self, sse_client):
        """POST /message with non-JSON body returns 400 + parse error."""
        resp = sse_client.post(
            "/message",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"]["code"] == -32700
        assert "Parse error" in data["error"]["message"]


def test_api_runtime_role_omits_indexing_tools_and_skips_graph_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API-only runtime should expose read-only MCP tools without indexing machinery."""

    monkeypatch.setenv("PCG_RUNTIME_ROLE", "api")

    with patch("platform_context_graph.mcp.server.get_database_manager") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        with (
            patch("platform_context_graph.mcp.server.JobManager") as mock_job_cls,
            patch(
                "platform_context_graph.mcp.server.GraphBuilder"
            ) as mock_graph_builder,
            patch("platform_context_graph.mcp.server.CodeFinder"),
            patch("platform_context_graph.mcp.server.CodeWatcher") as mock_code_watcher,
            patch(
                "platform_context_graph.mcp.server.EcosystemIndexer"
            ) as mock_ecosystem,
            patch("platform_context_graph.mcp.server.CrossRepoLinker") as mock_linker,
        ):
            server = MCPServer()

    tool_names = set(server.tools)

    assert "get_ingester_status" in tool_names
    assert "list_ingesters" in tool_names
    assert "find_code" in tool_names
    assert "add_code_to_graph" not in tool_names
    assert "watch_directory" not in tool_names
    assert "delete_repository" not in tool_names
    mock_job_cls.assert_not_called()
    mock_graph_builder.assert_not_called()
    mock_code_watcher.assert_not_called()
    mock_ecosystem.assert_not_called()
    mock_linker.assert_not_called()
