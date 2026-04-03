from __future__ import annotations

import json
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

import platform_context_graph.query as query_pkg
from platform_context_graph.domain import (
    AliasMetadata,
    EntityRef,
    ProblemDetails,
    ResponseEnvelope,
    ResolveEntityRequest,
)
from platform_context_graph.repository_identity import canonical_repository_id
from platform_context_graph.query.entity_resolution import resolve_entity

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "shared_infra"
    / "shared_rds_graph.json"
)


def load_shared_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_query_module_exports_are_present():
    from platform_context_graph.query import (
        code,
        compare,
        content,
        context,
        entity_resolution,
        impact,
        infra,
        repositories,
        status,
    )

    assert query_pkg.__all__ == [
        "code",
        "compare",
        "content",
        "context",
        "entity_resolution",
        "impact",
        "infra",
        "repositories",
        "status",
    ]
    assert query_pkg.code is code
    assert query_pkg.compare is compare
    assert query_pkg.content is content
    assert query_pkg.context is context
    assert query_pkg.entity_resolution is entity_resolution
    assert query_pkg.impact is impact
    assert query_pkg.infra is infra
    assert query_pkg.repositories is repositories
    assert query_pkg.status is status

    assert hasattr(entity_resolution, "resolve_entity")
    assert hasattr(context, "get_entity_context")
    assert hasattr(context, "get_workload_context")
    assert hasattr(context, "get_service_context")
    assert hasattr(code, "search_code")
    assert hasattr(code, "get_code_relationships")
    assert hasattr(code, "find_dead_code")
    assert hasattr(code, "get_complexity")
    assert hasattr(content, "get_file_content")
    assert hasattr(content, "get_entity_content")
    assert hasattr(repositories, "list_repositories")
    assert hasattr(repositories, "get_repository_context")
    assert hasattr(repositories, "get_repository_stats")
    assert hasattr(infra, "search_infra_resources")
    assert hasattr(infra, "get_infra_relationships")
    assert hasattr(infra, "get_ecosystem_overview")
    assert hasattr(impact, "trace_resource_to_code")
    assert hasattr(impact, "explain_dependency_path")
    assert hasattr(impact, "find_change_surface")
    assert hasattr(compare, "compare_environments")
    assert hasattr(status, "list_ingesters")
    assert hasattr(status, "get_ingester_status")
    assert hasattr(status, "request_ingester_scan")


def test_shared_service_signatures_stay_keyword_only_and_stable():
    from platform_context_graph.query import (
        code,
        compare,
        context,
        entity_resolution,
        impact,
        infra,
        repositories,
    )

    def assert_kwonly(fn, expected):
        params = list(inspect.signature(fn).parameters.values())
        assert params[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert params[0].name == "database"
        assert [param.name for param in params[1:]] == expected
        assert all(param.kind is inspect.Parameter.KEYWORD_ONLY for param in params[1:])

    assert_kwonly(
        entity_resolution.resolve_entity,
        ["query", "types", "kinds", "environment", "repo_id", "exact", "limit"],
    )
    assert_kwonly(context.get_entity_context, ["entity_id", "environment"])
    assert_kwonly(context.get_workload_context, ["workload_id", "environment"])
    assert_kwonly(context.get_service_context, ["workload_id", "environment"])
    assert_kwonly(
        code.search_code,
        ["query", "repo_id", "scope", "exact", "limit", "edit_distance"],
    )
    assert_kwonly(
        code.get_code_relationships,
        ["query_type", "target", "context", "repo_id", "scope"],
    )
    assert_kwonly(code.find_dead_code, ["repo_id", "scope", "exclude_decorated_with"])
    assert_kwonly(
        code.get_complexity,
        ["mode", "limit", "function_name", "path", "repo_id", "scope"],
    )
    assert_kwonly(repositories.get_repository_context, ["repo_id"])
    assert_kwonly(repositories.get_repository_stats, ["repo_id"])
    assert_kwonly(repositories.list_repositories, [])
    assert_kwonly(
        infra.search_infra_resources, ["query", "types", "environment", "limit"]
    )
    assert_kwonly(
        infra.get_infra_relationships, ["target", "relationship_type", "environment"]
    )
    assert_kwonly(impact.trace_resource_to_code, ["start", "environment", "max_depth"])
    assert_kwonly(impact.explain_dependency_path, ["source", "target", "environment"])
    assert_kwonly(impact.find_change_surface, ["target", "environment"])
    assert_kwonly(compare.compare_environments, ["workload_id", "left", "right"])


def test_workload_and_workload_instance_have_distinct_ids():
    workload = EntityRef(
        id="workload:payments-api", type="workload", kind="service", name="payments-api"
    )
    instance = EntityRef(
        id="workload-instance:payments-api:prod",
        type="workload_instance",
        kind="service",
        name="payments-api",
        environment="prod",
        workload_id="workload:payments-api",
    )
    assert workload.id != instance.id


def test_service_alias_is_not_a_distinct_entity_type():
    response = AliasMetadata(requested_as="service", canonical_type="workload")
    assert response.canonical_type == "workload"


def test_resolve_entity_request_defaults_match_the_spec():
    request = ResolveEntityRequest(query="payments")
    assert request.exact is False
    assert request.limit == 10
    assert request.query == "payments"


def test_resolve_entity_returns_ranked_matches_for_fuzzy_query():
    result = resolve_entity(
        FIXTURE_PATH,
        query="payments prod rds",
        types=["workload", "cloud_resource"],
        limit=5,
    )

    assert "matches" in result
    assert isinstance(result["matches"], list)
    assert len(result["matches"]) >= 2
    assert result["matches"][0]["ref"]["id"].startswith(
        ("workload:", "cloud-resource:")
    )
    assert "score" in result["matches"][0]
    assert result["matches"][0]["score"] >= result["matches"][-1]["score"]


def test_resolve_entity_honors_exact_kinds_repo_and_ambiguity():
    fixture = load_shared_fixture()
    payments_repo_id = "repository:r_5f4f4b74"

    ambiguous = resolve_entity(
        fixture,
        query="payments",
        types=["workload"],
        kinds=["service"],
        repo_id=payments_repo_id,
        exact=False,
        limit=2,
    )
    assert len(ambiguous["matches"]) == 2
    assert all(match["ref"]["type"] == "workload" for match in ambiguous["matches"])
    assert all(match["ref"]["kind"] == "service" for match in ambiguous["matches"])

    exact = resolve_entity(
        fixture,
        query="payments-api",
        types=["workload"],
        kinds=["service"],
        repo_id=payments_repo_id,
        exact=True,
        limit=2,
    )
    assert [match["ref"]["id"] for match in exact["matches"]] == [
        "workload:payments-api"
    ]


def test_resolve_entity_supports_repo_names_hostnames_and_service_aliases():
    fixture = {
        "entities": [
            {
                "id": canonical_repository_id(
                    remote_url="git@github.com:platformcontext/shared-data.git",
                    local_path="/srv/repos/shared-data",
                ),
                "type": "repository",
                "name": "shared-data",
                "repo_slug": "platformcontext/shared-data",
                "remote_url": "https://github.com/platformcontext/shared-data",
                "local_path": "/srv/repos/shared-data",
                "aliases": ["shared-data", "data-platform"],
            },
            {
                "id": "workload:payments-api",
                "type": "workload",
                "kind": "service",
                "name": "payments-api",
                "aliases": ["payments service", "payments-api"],
            },
            {
                "id": "cloud-resource:shared-payments-prod",
                "type": "cloud_resource",
                "name": "shared-payments-prod",
                "aliases": ["db.prod.internal", "payments prod rds"],
            },
        ],
        "edges": [],
    }

    repo_match = resolve_entity(
        fixture, query="shared-data", types=["repository"], exact=False
    )
    slug_match = resolve_entity(
        fixture,
        query="platformcontext/shared-data",
        types=["repository"],
        exact=False,
    )
    remote_match = resolve_entity(
        fixture,
        query="git@github.com:platformcontext/shared-data.git",
        types=["repository"],
        exact=False,
    )
    host_match = resolve_entity(
        fixture, query="db.prod.internal", types=["cloud_resource"], exact=False
    )
    alias_match = resolve_entity(
        fixture, query="payments service", types=["workload"], exact=False
    )

    expected_repo_id = canonical_repository_id(
        remote_url="git@github.com:platformcontext/shared-data.git",
        local_path="/srv/repos/shared-data",
    )
    assert repo_match["matches"][0]["ref"]["id"] == expected_repo_id
    assert slug_match["matches"][0]["ref"]["id"] == expected_repo_id
    assert remote_match["matches"][0]["ref"]["id"] == expected_repo_id
    assert "local_path" not in repo_match["matches"][0]["ref"]
    assert "local_path" not in slug_match["matches"][0]["ref"]
    assert "local_path" not in remote_match["matches"][0]["ref"]
    assert (
        host_match["matches"][0]["ref"]["id"] == "cloud-resource:shared-payments-prod"
    )
    assert alias_match["matches"][0]["ref"]["id"] == "workload:payments-api"
    assert alias_match["matches"][0]["alias"]["requested_as"] == "service"

    inference = host_match["matches"][0]["inference"]
    assert inference["confidence"] is not None
    assert inference["reason"]
    assert inference["evidence"]


def test_entity_ids_are_not_raw_paths_and_match_their_type_prefix():
    with pytest.raises(ValidationError):
        EntityRef(id="environment:prod", type="repository", name="payments-api")


def test_resolve_entity_accepts_hyphenated_type_filters():
    result = resolve_entity(
        FIXTURE_PATH,
        query="payments prod",
        types=["cloud-resource", "workload-instance"],
        limit=5,
    )

    assert result["matches"]
    assert all(
        match["ref"]["type"] in {"cloud_resource", "workload_instance"}
        for match in result["matches"]
    )


def test_resolve_entity_accepts_argocd_type_aliases():
    fixture = {
        "entities": [
            {
                "id": "k8s-resource:api-node-search",
                "type": "k8s_resource",
                "name": "api-node-search",
                "aliases": ["api-node-search"],
            }
        ],
        "edges": [],
    }

    result = resolve_entity(
        fixture,
        query="api-node-search",
        types=["argocd_application", "argocd_applicationset"],
        limit=5,
    )

    assert [match["ref"]["id"] for match in result["matches"]] == [
        "k8s-resource:api-node-search"
    ]
    assert result["matches"][0]["ref"]["type"] == "k8s_resource"


def test_resolve_entity_discovers_live_workloads_from_runtime_and_argocd_metadata():
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
            if "MATCH (w:Workload)" in query:
                return FakeResult(records=[])
            if "MATCH (i:WorkloadInstance)" in query:
                return FakeResult(records=[])
            if (
                "MATCH (repo:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(k:K8sResource)"
                in query
            ):
                return FakeResult(
                    records=[
                        {
                            "name": "api-node-search",
                            "resource_kinds": ["Deployment"],
                            "namespaces": ["api-node"],
                            "repo_ids": ["repository:r_5c50d0d3"],
                            "repo_names": ["api-node-search"],
                            "repo_slugs": ["boatsgroup/api-node-search"],
                            "remote_urls": [
                                "https://github.com/boatsgroup/api-node-search"
                            ],
                        }
                    ]
                )
            if "MATCH (app)-[:SOURCES_FROM]->(repo:Repository)" in query:
                return FakeResult(
                    records=[
                        {
                            "name": "api-node-search",
                            "app_kinds": ["applicationset"],
                            "repo_ids": ["repository:r_20871f7f"],
                            "repo_names": ["helm-charts"],
                            "repo_slugs": ["boatsgroup/helm-charts"],
                            "remote_urls": [
                                "https://github.com/boatsgroup/helm-charts"
                            ],
                        }
                    ]
                )
            raise AssertionError(f"unexpected query: {query}")

    db = MagicMock()
    db.get_driver.return_value.session.return_value = FakeSession()

    result = resolve_entity(db, query="api-node-search", types=["workload"], limit=5)

    assert [match["ref"]["id"] for match in result["matches"]] == [
        "workload:api-node-search"
    ]
    assert result["matches"][0]["ref"]["type"] == "workload"
    assert result["matches"][0]["ref"]["kind"] == "service"


def test_resolve_entity_matches_graph_backed_workload_instances_by_exact_id():
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
                return FakeResult(records=[])
            if "MATCH (w:Workload)" in query:
                return FakeResult(records=[])
            if "MATCH (i:WorkloadInstance)" in query:
                return FakeResult(
                    records=[
                        {
                            "id": "workload-instance:api-node-search:bg-qa",
                            "name": "api-node-search",
                            "kind": "service",
                            "environment": "bg-qa",
                            "workload_id": "workload:api-node-search",
                            "repo_id": "repository:r_5c50d0d3",
                            "repo_slug": "boatsgroup/api-node-search",
                            "remote_url": "https://github.com/boatsgroup/api-node-search",
                        }
                    ]
                )
            raise AssertionError(f"unexpected query: {query}")

    db = MagicMock()
    db.get_driver.return_value.session.return_value = FakeSession()

    result = resolve_entity(
        db,
        query="workload-instance:api-node-search:bg-qa",
        types=["workload_instance"],
        exact=True,
        limit=5,
    )

    assert [match["ref"]["id"] for match in result["matches"]] == [
        "workload-instance:api-node-search:bg-qa"
    ]


def test_valid_canonical_repository_ref_uses_the_expected_prefix():
    ref = EntityRef(
        id="repository:r_ab12cd34",
        type="repository",
        name="payments-api",
        local_path="/srv/repos/payments-api",
        repo_slug="platformcontext/payments-api",
        remote_url="https://github.com/platformcontext/payments-api",
        has_remote=True,
    )
    assert ref.id == "repository:r_ab12cd34"
    assert ref.id.startswith("repository:")
    assert "/" not in ref.id


def test_workload_instance_requires_a_canonical_workload_id():
    with pytest.raises(ValidationError):
        EntityRef(
            id="workload-instance:payments-api:prod",
            type="workload_instance",
            kind="service",
            name="payments-api",
            environment="prod",
            workload_id="repository:r_ab12cd34",
        )

    with pytest.raises(ValidationError):
        EntityRef(
            id="workload-instance:payments-api:prod",
            type="workload_instance",
            kind="service",
            name="payments-api",
            environment="prod",
            workload_id="/srv/repos/payments-api",
        )


def test_entity_ids_are_not_raw_paths_and_are_url_safe():
    with pytest.raises(ValidationError):
        EntityRef(
            id="/srv/repos/payments-api",
            type="repository",
            name="payments-api",
            local_path="/srv/repos/payments-api",
        )


def test_workload_instance_requires_canonical_relationship_fields():
    with pytest.raises(ValidationError):
        EntityRef(
            id="workload-instance:payments-api:prod",
            type="workload_instance",
            kind="service",
            name="payments-api",
        )


def test_response_envelope_enforces_one_of_data_or_problem():
    ok = ResponseEnvelope[ResolveEntityRequest](
        data=ResolveEntityRequest(query="payments")
    )
    assert ok.data is not None
    assert ok.problem is None

    failed = ResponseEnvelope[ResolveEntityRequest](
        problem=ProblemDetails(title="bad request", status=400)
    )
    assert failed.data is None
    assert failed.problem is not None

    with pytest.raises(ValidationError):
        ResponseEnvelope[ResolveEntityRequest]()

    with pytest.raises(ValidationError):
        ResponseEnvelope[ResolveEntityRequest](
            data=ResolveEntityRequest(query="payments"),
            problem=ProblemDetails(title="bad request", status=400),
        )


def test_non_workload_entities_do_not_accept_workload_specific_fields():
    with pytest.raises(ValidationError):
        EntityRef(
            id="repository:r_ab12cd34",
            type="repository",
            name="payments-api",
            workload_id="workload:payments-api",
        )


def test_valid_canonical_repository_ref_keeps_url_safe_id():
    ref = EntityRef(
        id="repository:r_ab12cd34",
        type="repository",
        name="payments-api",
        local_path="/srv/repos/payments-api",
        repo_slug="platformcontext/payments-api",
        remote_url="https://github.com/platformcontext/payments-api",
        has_remote=True,
    )
    assert "/" not in ref.id
    assert ref.id != ref.local_path
