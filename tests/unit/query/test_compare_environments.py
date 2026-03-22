from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from platform_context_graph.query.compare import compare_environments

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
                if isinstance(result, dict) and "by_id" in result:
                    return result["by_id"].get(kwargs.get("id"), MockResult())
                return result
        return MockResult()

    session.run = mock_run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver
    return db


def test_compare_environments_reports_changed_resources_for_shared_rds_workload():
    fixture = load_shared_fixture()

    result = compare_environments(
        fixture,
        workload_id="workload:payments-api",
        left="stage",
        right="prod",
    )

    assert result["workload"]["id"] == "workload:payments-api"
    assert result["left"]["environment"] == "stage"
    assert result["right"]["environment"] == "prod"
    assert result["right"]["instance"]["id"] == "workload-instance:payments-api:prod"
    assert (
        result["changed"]["cloud_resources"][0]["id"]
        == "cloud-resource:shared-payments-prod"
    )
    assert result["confidence"] > 0
    assert result["reason"]
    assert result["evidence"]


def test_compare_environments_reports_removed_only_diffs_with_summary_metadata():
    fixture = load_shared_fixture()

    result = compare_environments(
        fixture,
        workload_id="workload:payments-api",
        left="prod",
        right="stage",
    )

    assert result["changed"]["cloud_resources"]
    assert result["changed"]["cloud_resources"][0]["change"] == "removed"
    assert result["confidence"] > 0
    assert result["reason"] != "No differences found between prod and stage"
    assert result["evidence"]


def test_compare_environments_attaches_metadata_to_changed_cloud_resources():
    fixture = load_shared_fixture()

    result = compare_environments(
        fixture,
        workload_id="workload:payments-api",
        left="stage",
        right="prod",
    )

    changed = result["changed"]["cloud_resources"][0]
    assert changed["id"] == "cloud-resource:shared-payments-prod"
    assert changed["confidence"] > 0
    assert changed["reason"]
    assert changed["evidence"]


def test_compare_environments_returns_neutral_summary_when_environments_match():
    fixture = load_shared_fixture()

    result = compare_environments(
        fixture,
        workload_id="workload:payments-api",
        left="prod",
        right="prod",
    )

    assert result["changed"]["cloud_resources"] == []
    assert result["confidence"] == 0.0
    assert result["evidence"] == []
    assert result["reason"] == "No differences found between prod and prod"


def test_compare_environments_returns_missing_shape_when_workload_is_missing_or_unresolved():
    fixture = load_shared_fixture()

    missing = compare_environments(
        fixture, workload_id=None, left="stage", right="prod"
    )
    unresolved = compare_environments(
        fixture,
        workload_id="workload:does-not-exist",
        left="stage",
        right="prod",
    )

    assert missing["workload"] is None
    assert missing["left"]["status"] == "missing"
    assert "workload_id" in missing["reason"]
    assert unresolved["workload"] is None
    assert unresolved["left"]["status"] == "missing"
    assert "not found" in unresolved["reason"]


def test_compare_environments_has_minimal_db_backed_fallback():
    db = make_mock_db(
        {
            "MATCH (w:Workload) WHERE w.id = $id": {
                "by_id": {
                    "workload:payments-api": MockResult(
                        single_record=MockRecord(
                            {
                                "id": "workload:payments-api",
                                "name": "payments-api",
                                "kind": "service",
                                "repo_id": "repository:r_5f4f4b74",
                            }
                        )
                    )
                }
            },
            "MATCH (i:WorkloadInstance) WHERE i.id = $id": {
                "by_id": {
                    "workload-instance:payments-api:prod": MockResult(
                        single_record=MockRecord(
                            {
                                "id": "workload-instance:payments-api:prod",
                                "name": "payments-api",
                                "kind": "service",
                                "environment": "prod",
                                "workload_id": "workload:payments-api",
                                "repo_id": "repository:r_5f4f4b74",
                            }
                        )
                    )
                }
            },
            "WHERE source.id = $id OR target.id = $id": {
                "by_id": {
                    "workload-instance:payments-api:prod": MockResult(
                        records=[
                            {
                                "source": "workload-instance:payments-api:prod",
                                "source_type": "workload_instance",
                                "target": "cloud-resource:shared-payments-prod",
                                "target_type": "cloud_resource",
                                "type": "USES",
                                "confidence": 0.92,
                                "reason": "Prod instance points at the shared RDS hostname",
                                "evidence": [
                                    {
                                        "source": "helm-values",
                                        "detail": "database.host=db.prod.internal",
                                        "weight": 0.92,
                                    }
                                ],
                            }
                        ]
                    )
                }
            },
        }
    )

    result = compare_environments(
        db, workload_id="workload:payments-api", left="stage", right="prod"
    )

    assert result["right"]["instance"]["id"] == "workload-instance:payments-api:prod"
    assert (
        result["changed"]["cloud_resources"][0]["id"]
        == "cloud-resource:shared-payments-prod"
    )
    assert result["confidence"] > 0


def test_compare_environments_discovers_db_backed_instance_by_workload_and_environment():
    db = MagicMock()
    driver = MagicMock()
    session = MagicMock()

    def mock_run(query, **kwargs):
        if "MATCH (w:Workload)" in query:
            return MockResult(
                single_record=MockRecord(
                    {
                        "id": "workload:payments-api",
                        "name": "payments-api",
                        "kind": "service",
                        "repo_id": "repository:r_5f4f4b74",
                    }
                )
            )
        if (
            "MATCH (i:WorkloadInstance)" in query
            and "i.workload_id = $workload_id" in query
            and "($environment IS NULL OR i.environment = $environment)" in query
        ):
            if kwargs == {
                "workload_id": "workload:payments-api",
                "environment": "prod",
            }:
                return MockResult(
                    records=[
                        {
                            "id": "workload-instance:payments-api-live:prod",
                            "name": "payments-api-live",
                            "kind": "service",
                            "environment": "prod",
                            "workload_id": "workload:payments-api",
                            "repo_id": "repository:r_5f4f4b74",
                        }
                    ]
                )
        if "WHERE source.id = $id OR target.id = $id" in query:
            if kwargs.get("id") == "workload-instance:payments-api-live:prod":
                return MockResult(
                    records=[
                        {
                            "source": "workload-instance:payments-api-live:prod",
                            "source_type": "workload_instance",
                            "target": "cloud-resource:shared-payments-prod",
                            "target_type": "cloud_resource",
                            "type": "USES",
                            "confidence": 0.92,
                            "reason": "Payments API live instance points at the shared production RDS hostname",
                            "evidence": [
                                {
                                    "source": "helm-values",
                                    "detail": "database.host=db.prod.internal",
                                    "weight": 0.92,
                                }
                            ],
                        }
                    ]
                )
        return MockResult()

    session.run = mock_run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver

    result = compare_environments(
        db, workload_id="workload:payments-api", left="prod", right="prod"
    )

    assert result["left"]["status"] == "present"
    assert result["right"]["status"] == "present"
    assert (
        result["left"]["instance"]["id"] == "workload-instance:payments-api-live:prod"
    )
    assert (
        result["right"]["instance"]["id"] == "workload-instance:payments-api-live:prod"
    )
    assert (
        result["right"]["cloud_resources"][0]["id"]
        == "cloud-resource:shared-payments-prod"
    )
    assert result["changed"]["cloud_resources"] == []
