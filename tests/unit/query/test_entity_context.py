from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from platform_context_graph.domain.responses import EntityContextResponse
from platform_context_graph.query.context import get_entity_context

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "shared_infra"
    / "shared_rds_graph.json"
)


def load_shared_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


class MockRecord:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data.get(key)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()


class MockResult:
    def __init__(self, records=None, single_record=None):
        self._records = records or []
        self._single_record = single_record

    def single(self):
        return self._single_record

    def data(self):
        return self._records


def make_mock_db(query_results):
    db = MagicMock()
    driver = MagicMock()
    session = MagicMock()

    def mock_run(query, **kwargs):
        for substr, result in query_results.items():
            if substr in query:
                return result
        return MockResult()

    session.run = mock_run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver
    return db


def test_get_entity_context_handles_workload_and_workload_instance_ids():
    fixture = load_shared_fixture()

    workload = get_entity_context(fixture, entity_id="workload:payments-api")
    instance = get_entity_context(
        fixture,
        entity_id="workload-instance:payments-api:prod",
    )

    assert workload["entity"]["id"] == "workload:payments-api"
    assert workload["workload"]["id"] == "workload:payments-api"

    assert instance["entity"]["id"] == "workload-instance:payments-api:prod"
    assert instance["workload"]["id"] == "workload:payments-api"
    assert instance["instance"]["id"] == "workload-instance:payments-api:prod"


def test_get_entity_context_has_minimal_db_backed_workload_fallback():
    db = make_mock_db(
        {
            "MATCH (r:Repository)\n            WHERE r.name CONTAINS $name\n            RETURN r.name as name, r.path as path": MockResult(
                single_record=MockRecord(
                    {
                        "name": "payments-platform",
                        "path": "/srv/repos/payments-platform",
                    }
                )
            ),
            "MATCH (k:K8sResource)\n            WHERE k.name CONTAINS $name": MockResult(
                records=[
                    {
                        "name": "payments-api",
                        "kind": "Deployment",
                        "namespace": "payments",
                    }
                ]
            ),
        }
    )

    workload = get_entity_context(db, entity_id="workload:payments-api")
    instance = get_entity_context(db, entity_id="workload-instance:payments-api:prod")

    assert workload["entity"]["id"] == "workload:payments-api"
    assert workload["workload"]["id"] == "workload:payments-api"
    assert instance["entity"]["id"] == "workload-instance:payments-api:prod"
    assert instance["instance"]["id"] == "workload-instance:payments-api:prod"


def test_db_backed_workload_instance_context_validates_against_entity_response_model():
    db = make_mock_db(
        {
            "MATCH (r:Repository)\n            WHERE r.name CONTAINS $name\n            RETURN r.name as name, r.path as path": MockResult(
                single_record=MockRecord(
                    {
                        "name": "payments-platform",
                        "path": "/srv/repos/payments-platform",
                    }
                )
            ),
            "MATCH (k:K8sResource)\n            WHERE k.name CONTAINS $name": MockResult(
                records=[
                    {
                        "name": "payments-api",
                        "kind": "Deployment",
                        "namespace": "payments",
                    }
                ]
            ),
        }
    )

    result = get_entity_context(db, entity_id="workload-instance:payments-api:prod")
    validated = EntityContextResponse.model_validate(result)

    assert validated.entity.id == "workload-instance:payments-api:prod"
    assert validated.entity.kind == "service"
    assert validated.instance is not None
    assert validated.instance.id == "workload-instance:payments-api:prod"


def test_get_entity_context_supports_content_entities(monkeypatch):
    db = make_mock_db(
        {
            "WHERE r.id = $id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "repository:r_ab12cd34",
                        "name": "payments-api",
                        "path": "/srv/repos/payments-api",
                        "local_path": "/srv/repos/payments-api",
                        "repo_slug": "platformcontext/payments-api",
                        "remote_url": "https://github.com/platformcontext/payments-api",
                        "has_remote": True,
                    }
                )
            )
        }
    )
    monkeypatch.setattr(
        "platform_context_graph.query.context.content_entity.get_content_service",
        lambda _database: MagicMock(
            get_entity_content=lambda *, entity_id: {
                "available": True,
                "entity_id": entity_id,
                "repo_id": "repository:r_ab12cd34",
                "relative_path": "src/payments.py",
                "entity_type": "Function",
                "entity_name": "process_payment",
                "start_line": 10,
                "end_line": 18,
                "content": "def process_payment():\n    return True\n",
                "language": "python",
                "source_backend": "postgres",
            }
        ),
    )

    result = get_entity_context(db, entity_id="content-entity:e_ab12cd34ef56")
    validated = EntityContextResponse.model_validate(result)

    assert validated.entity.id == "content-entity:e_ab12cd34ef56"
    assert validated.entity.type == "content_entity"
    assert validated.repositories[0].id == "repository:r_ab12cd34"
    assert result["relative_path"] == "src/payments.py"


def test_content_entity_context_summarizes_declared_and_observed_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Content-entity context should expose a compact lineage evidence summary."""

    db = make_mock_db(
        {
            "WHERE r.id = $id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "repository:r_ab12cd34",
                        "name": "analytics-warehouse",
                        "path": "/srv/repos/analytics-warehouse",
                        "local_path": "/srv/repos/analytics-warehouse",
                        "repo_slug": "platformcontext/analytics-warehouse",
                        "remote_url": "https://github.com/platformcontext/analytics-warehouse",
                        "has_remote": True,
                    }
                )
            ),
            "WHERE coalesce(source.id, source.uid) = $id": MockResult(
                records=[
                    {
                        "source_id": "content-entity:e_ab12cd34ef56",
                        "source_uid": "content-entity:e_ab12cd34ef56",
                        "source_path": "/srv/repos/analytics-warehouse/models/order_metrics.sql",
                        "source_labels": ["DataAsset"],
                        "target_id": "data-asset:warehouse:raw.orders",
                        "target_uid": None,
                        "target_path": "/warehouse/raw/orders.sql",
                        "target_labels": ["DataAsset"],
                        "type": "ASSET_DERIVES_FROM",
                        "confidence": 0.93,
                        "reason": "Model derives from raw.orders",
                        "evidence": [
                            {
                                "source": "compiled-sql",
                                "detail": "select * from raw.orders",
                                "weight": 0.93,
                            }
                        ],
                    },
                    {
                        "source_id": "query-execution:warehouse:query-123",
                        "source_uid": None,
                        "source_path": "/warehouse/query-history/query-123.json",
                        "source_labels": ["QueryExecution"],
                        "target_id": "content-entity:e_ab12cd34ef56",
                        "target_uid": "content-entity:e_ab12cd34ef56",
                        "target_path": "/srv/repos/analytics-warehouse/models/order_metrics.sql",
                        "target_labels": ["DataAsset"],
                        "type": "RUNS_QUERY_AGAINST",
                        "confidence": 0.91,
                        "reason": "Warehouse replay observed a query against order_metrics",
                        "evidence": [
                            {
                                "source": "warehouse-replay",
                                "detail": "query-123 touched order_metrics",
                                "weight": 0.91,
                            }
                        ],
                    },
                ]
            ),
        }
    )
    monkeypatch.setattr(
        "platform_context_graph.query.context.content_entity.get_content_service",
        lambda _database: MagicMock(
            get_entity_content=lambda *, entity_id: {
                "available": True,
                "entity_id": entity_id,
                "repo_id": "repository:r_ab12cd34",
                "relative_path": "models/order_metrics.sql",
                "entity_type": "DataAsset",
                "entity_name": "analytics.order_metrics",
                "start_line": 1,
                "end_line": 12,
                "content": "select * from raw.orders\n",
                "language": "sql",
                "source_backend": "postgres",
            }
        ),
    )

    result = get_entity_context(db, entity_id="content-entity:e_ab12cd34ef56")

    assert result["lineage_evidence"] == {
        "status": "combined",
        "evidence_sources": ["declared_lineage", "observed_lineage"],
    }


def test_get_entity_context_supports_data_assets() -> None:
    """Entity context should support generic data-intelligence entities."""

    db = make_mock_db(
        {
            "MATCH (entity)\n            WHERE entity.id = $entity_id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "data-asset:warehouse:finance.revenue",
                        "name": "finance.revenue",
                        "type": "data_asset",
                        "path": "/srv/repos/analytics/models/finance/revenue.sql",
                        "repo_id": "repository:r_analytics",
                        "relative_path": "models/finance/revenue.sql",
                    }
                )
            ),
            "WHERE r.id = $repo_id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "repository:r_analytics",
                        "name": "analytics-platform",
                        "path": "/srv/repos/analytics-platform",
                        "local_path": "/srv/repos/analytics-platform",
                        "repo_slug": "platformcontext/analytics-platform",
                        "remote_url": "https://github.com/platformcontext/analytics-platform",
                        "has_remote": True,
                    }
                )
            ),
        }
    )

    result = get_entity_context(db, entity_id="data-asset:warehouse:finance.revenue")
    validated = EntityContextResponse.model_validate(result)

    assert validated.entity.id == "data-asset:warehouse:finance.revenue"
    assert validated.entity.type == "data_asset"
    assert validated.repositories[0].id == "repository:r_analytics"
    assert result["relative_path"] == "models/finance/revenue.sql"


def test_get_entity_context_enriches_data_entities_with_persona_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Data-entity context should expose a compact impact and governance summary."""

    db = make_mock_db(
        {
            "MATCH (entity)\n            WHERE entity.id = $entity_id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "data-asset:analytics.finance.daily_revenue",
                        "name": "analytics.finance.daily_revenue",
                        "type": "data_asset",
                        "path": "/srv/repos/analytics/models/finance/daily_revenue.sql",
                        "repo_id": "repository:r_analytics",
                        "relative_path": "models/finance/daily_revenue.sql",
                    }
                )
            ),
            "WHERE r.id = $repo_id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "repository:r_analytics",
                        "name": "analytics-platform",
                        "path": "/srv/repos/analytics-platform",
                        "local_path": "/srv/repos/analytics-platform",
                        "repo_slug": "platformcontext/analytics-platform",
                        "remote_url": "https://github.com/platformcontext/analytics-platform",
                        "has_remote": True,
                    }
                )
            ),
        }
    )

    monkeypatch.setattr(
        "platform_context_graph.query.context.data_entity.db_fetch_entity",
        lambda _database, _entity_id: {
            "id": "data-asset:analytics.finance.daily_revenue",
            "type": "data_asset",
            "name": "analytics.finance.daily_revenue",
            "path": "/srv/repos/analytics/models/finance/daily_revenue.sql",
            "repo_id": "repository:r_analytics",
            "owner_names": ["Finance Analytics"],
            "owner_teams": ["Finance Analytics"],
            "contract_names": ["daily_revenue_contract"],
            "contract_levels": ["gold"],
            "change_policies": ["additive"],
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.context.data_entity.db_fetch_edges",
        lambda _database, _entity_id: [
            {
                "from": "analytics-model:finance:daily_revenue_model",
                "to": "data-asset:analytics.finance.daily_revenue",
                "type": "COMPILES_TO",
                "confidence": 0.94,
                "reason": "Compiled SQL produces the daily revenue asset",
                "evidence": [],
            },
            {
                "from": "query-execution:warehouse:query-123",
                "to": "data-asset:analytics.finance.daily_revenue",
                "type": "RUNS_QUERY_AGAINST",
                "confidence": 0.91,
                "reason": "Warehouse replay observed a query against daily revenue",
                "evidence": [],
            },
        ],
    )
    monkeypatch.setattr(
        "platform_context_graph.query.context.data_entity.find_change_surface",
        lambda _database, *, target, environment=None: {
            "target": {
                "id": target,
                "type": "data_asset",
                "name": "analytics.finance.daily_revenue",
            },
            "target_change_classification": {
                "primary": "additive",
                "signals": ["additive"],
                "reasons": ["Contract change policy marks this entity as additive."],
            },
            "classification_summary": {
                "highest": "quality-risk",
                "counts": {
                    "governance-sensitive": 0,
                    "breaking": 0,
                    "quality-risk": 1,
                    "additive": 0,
                    "informational": 2,
                },
            },
            "impacted": [
                {
                    "entity": {
                        "id": "data-quality-check:finance:gross-amount-non-negative",
                        "type": "data_quality_check",
                        "name": "gross_amount_non_negative",
                    }
                },
                {
                    "entity": {
                        "id": "dashboard-asset:finance:revenue-overview",
                        "type": "dashboard_asset",
                        "name": "Revenue Overview",
                    }
                },
                {
                    "entity": {
                        "id": "data-column:semantic.finance.revenue_semantic.gross_amount",
                        "type": "data_column",
                        "name": "semantic.finance.revenue_semantic.gross_amount",
                    }
                },
            ],
        },
    )

    result = get_entity_context(
        db,
        entity_id="data-asset:analytics.finance.daily_revenue",
    )

    assert result["lineage_evidence"] == {
        "status": "combined",
        "evidence_sources": ["declared_lineage", "observed_lineage"],
    }
    assert result["data_intelligence"]["change_classification"]["primary"] == "additive"
    assert result["data_intelligence"]["highest_downstream_classification"] == (
        "quality-risk"
    )
    assert result["data_intelligence"]["downstream_counts"] == {
        "analytics_model_count": 0,
        "data_asset_count": 0,
        "data_column_count": 1,
        "query_execution_count": 0,
        "dashboard_asset_count": 1,
        "data_quality_check_count": 1,
    }
    assert result["data_intelligence"]["ownership"]["owner_teams"] == [
        "Finance Analytics"
    ]
    assert result["data_intelligence"]["contracts"]["contract_levels"] == ["gold"]
    assert [item["id"] for item in result["data_intelligence"]["sample_impacted_entities"]] == [
        "dashboard-asset:finance:revenue-overview",
        "data-quality-check:finance:gross-amount-non-negative",
        "data-column:semantic.finance.revenue_semantic.gross_amount",
    ]
    assert "1 dashboard" in result["data_intelligence"]["summary"]
    assert "1 quality check" in result["data_intelligence"]["summary"]
    assert "owners: Finance Analytics" in result["data_intelligence"]["summary"]


def test_get_entity_context_surfaces_partial_analytics_model_lineage_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Analytics-model context should explain why compiled lineage is partial."""

    db = make_mock_db(
        {
            "MATCH (entity)\n            WHERE entity.id = $entity_id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "analytics-model:model.jaffle_shop.orders_expanded",
                        "name": "orders_expanded",
                        "type": "analytics_model",
                        "path": (
                            "/srv/repos/analytics/target/compiled/jaffle_shop/"
                            "models/marts/orders_expanded.sql"
                        ),
                        "repo_id": "repository:r_analytics",
                        "relative_path": (
                            "target/compiled/jaffle_shop/models/marts/"
                            "orders_expanded.sql"
                        ),
                    }
                )
            ),
            "WHERE r.id = $repo_id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "repository:r_analytics",
                        "name": "analytics-platform",
                        "path": "/srv/repos/analytics-platform",
                        "local_path": "/srv/repos/analytics-platform",
                        "repo_slug": "platformcontext/analytics-platform",
                        "remote_url": "https://github.com/platformcontext/analytics-platform",
                        "has_remote": True,
                    }
                )
            ),
        }
    )

    monkeypatch.setattr(
        "platform_context_graph.query.context.data_entity.db_fetch_entity",
        lambda _database, _entity_id: {
            "id": "analytics-model:model.jaffle_shop.orders_expanded",
            "type": "analytics_model",
            "name": "orders_expanded",
            "path": (
                "/srv/repos/analytics/target/compiled/jaffle_shop/models/marts/"
                "orders_expanded.sql"
            ),
            "repo_id": "repository:r_analytics",
            "parse_state": "partial",
            "confidence": 0.5,
            "materialization": "table",
            "projection_count": 2,
            "unresolved_reference_count": 1,
            "unresolved_reference_reasons": ["wildcard_projection_not_supported"],
            "unresolved_reference_expressions": ["o.*"],
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.context.data_entity.db_fetch_edges",
        lambda _database, _entity_id: [
            {
                "from": "analytics-model:model.jaffle_shop.orders_expanded",
                "to": "data-asset:analytics.public.orders_expanded",
                "type": "COMPILES_TO",
                "confidence": 1.0,
                "reason": "Compiled SQL materializes the orders_expanded asset",
                "evidence": [],
            }
        ],
    )
    monkeypatch.setattr(
        "platform_context_graph.query.context.data_entity.find_change_surface",
        lambda _database, *, target, environment=None: {
            "target": {
                "id": target,
                "type": "analytics_model",
                "name": "orders_expanded",
            },
            "target_change_classification": {
                "primary": "informational",
                "signals": ["informational"],
                "reasons": ["Compiled lineage metadata is incomplete."],
            },
            "classification_summary": {
                "highest": "informational",
                "counts": {
                    "governance-sensitive": 0,
                    "breaking": 0,
                    "quality-risk": 0,
                    "additive": 0,
                    "informational": 0,
                },
            },
            "impacted": [],
        },
    )

    result = get_entity_context(
        db,
        entity_id="analytics-model:model.jaffle_shop.orders_expanded",
    )

    assert result["data_intelligence"]["lineage_coverage"] == {
        "state": "partial",
        "confidence": 0.5,
        "materialization": "table",
        "projection_count": 2,
        "unresolved_reference_count": 1,
        "unresolved_reference_reasons": ["wildcard_projection_not_supported"],
        "unresolved_reference_expressions": ["o.*"],
    }
    assert "compiled lineage is partial" in result["data_intelligence"]["summary"]
    assert "wildcard projection not supported" in result["data_intelligence"][
        "summary"
    ]
    assert "o.*" in result["data_intelligence"]["summary"]


def test_get_entity_context_surfaces_column_lineage_transform_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Data-column context should surface supported lineage transforms."""

    db = make_mock_db(
        {
            "MATCH (entity)\n            WHERE entity.id = $entity_id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "data-column:analytics.public.order_metrics.customer_name",
                        "name": "analytics.public.order_metrics.customer_name",
                        "type": "data_column",
                        "path": (
                            "/srv/repos/analytics/target/compiled/jaffle_shop/models/"
                            "marts/order_metrics.sql"
                        ),
                        "repo_id": "repository:r_analytics",
                        "relative_path": (
                            "target/compiled/jaffle_shop/models/marts/"
                            "order_metrics.sql"
                        ),
                    }
                )
            ),
            "WHERE r.id = $repo_id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "repository:r_analytics",
                        "name": "analytics-platform",
                        "path": "/srv/repos/analytics-platform",
                        "local_path": "/srv/repos/analytics-platform",
                        "repo_slug": "platformcontext/analytics-platform",
                        "remote_url": "https://github.com/platformcontext/analytics-platform",
                        "has_remote": True,
                    }
                )
            ),
        }
    )

    monkeypatch.setattr(
        "platform_context_graph.query.context.data_entity.db_fetch_entity",
        lambda _database, _entity_id: {
            "id": "data-column:analytics.public.order_metrics.customer_name",
            "type": "data_column",
            "name": "analytics.public.order_metrics.customer_name",
            "path": (
                "/srv/repos/analytics/target/compiled/jaffle_shop/models/marts/"
                "order_metrics.sql"
            ),
            "repo_id": "repository:r_analytics",
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.context.data_entity.db_fetch_edges",
        lambda _database, _entity_id: [
            {
                "from": "data-column:analytics.public.order_metrics.customer_name",
                "to": "data-column:raw.public.customers.full_name",
                "type": "COLUMN_DERIVES_FROM",
                "confidence": 0.95,
                "reason": "Compiled SQL applies upper() to the source column",
                "evidence": [],
                "transform_kind": "upper",
                "transform_expression": "upper(source_customer_name)",
            }
        ],
    )
    monkeypatch.setattr(
        "platform_context_graph.query.context.data_entity.find_change_surface",
        lambda _database, *, target, environment=None: {
            "target": {
                "id": target,
                "type": "data_column",
                "name": "analytics.public.order_metrics.customer_name",
            },
            "target_change_classification": {
                "primary": "informational",
                "signals": ["informational"],
                "reasons": ["No downstream consumers are indexed in this fixture."],
            },
            "classification_summary": {
                "highest": "informational",
                "counts": {
                    "governance-sensitive": 0,
                    "breaking": 0,
                    "quality-risk": 0,
                    "additive": 0,
                    "informational": 0,
                },
            },
            "impacted": [],
        },
    )

    result = get_entity_context(
        db,
        entity_id="data-column:analytics.public.order_metrics.customer_name",
    )

    assert result["data_intelligence"]["lineage_transforms"] == [
        {
            "direction": "upstream",
            "kind": "upper",
            "expression": "upper(source_customer_name)",
            "related_entity_id": "data-column:raw.public.customers.full_name",
            "related_name": "raw.public.customers.full_name",
        }
    ]
    assert "supported upstream transforms: upper" in result["data_intelligence"][
        "summary"
    ]
