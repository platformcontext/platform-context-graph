"""Focused entity-context tests for observed data-asset usage signals."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from platform_context_graph.query.context import get_entity_context


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


def test_get_entity_context_surfaces_observed_hot_usage_for_data_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Data-asset context should classify hot observed usage from replay edges."""

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
                        "entity_type": "DataAsset",
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
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.context.data_entity.db_fetch_edges",
        lambda _database, _entity_id: [
            {
                "from": "query-execution:warehouse:q_001",
                "to": "data-asset:analytics.finance.daily_revenue",
                "type": "RUNS_QUERY_AGAINST",
                "confidence": 0.91,
                "reason": "Warehouse replay observed a build query against daily revenue",
                "evidence": [],
            },
            {
                "from": "query-execution:warehouse:q_002",
                "to": "data-asset:analytics.finance.daily_revenue",
                "type": "RUNS_QUERY_AGAINST",
                "confidence": 0.89,
                "reason": "Warehouse replay observed a dashboard lookup against daily revenue",
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
        entity_id="data-asset:analytics.finance.daily_revenue",
    )

    assert result["data_intelligence"]["observed_usage"] == {
        "query_execution_count": 2,
        "usage_level": "hot",
        "query_execution_ids": [
            "query-execution:warehouse:q_001",
            "query-execution:warehouse:q_002",
        ],
    }
    assert (
        "observed usage is hot across 2 warehouse query executions"
        in result["data_intelligence"]["summary"]
    )
