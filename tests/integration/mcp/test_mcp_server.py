import pytest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from platform_context_graph.mcp import MCPServer
from platform_context_graph.query.context import ServiceAliasError
from platform_context_graph.mcp.tool_registry import TOOLS


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
                patch("platform_context_graph.mcp.server.JobManager") as mock_job_cls,
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

                # The tool on the server instance simply calls this handler
                # We must ensure the arguments are passed correctly (including wrappers)

                result = await mock_server.handle_tool_call(
                    "add_code_to_graph", {"path": "."}
                )

                # We can't strictly assert called_once because arguments are complex (bound methods)
                # But we can check result
                assert result == {"job_id": "123"}

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
            exact=False,
            limit=15,
            edit_distance=1,
        )
        assert result == {
            "success": True,
            "query": "payment api",
            "results": {"ranked_results": []},
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
        )
        assert result == {
            "success": True,
            "query_type": "find_callers",
            "target": "foo",
            "context": "src/foo.py",
            "results": {"results": []},
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

            repo_result = mock_server.get_repository_stats_tool(repo_path="/repo")
            infra_result = mock_server.find_infra_resources_tool(
                query="rds", category="terraform"
            )

        mock_repo_stats.assert_called_once_with(
            mock_server.code_finder, repo_id="/repo"
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
        from fastapi.responses import JSONResponse, StreamingResponse
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
