from __future__ import annotations

import re
from unittest.mock import MagicMock

from platform_context_graph.query.repositories import (
    _canonical_repository_id,
    get_repository_context,
    get_repository_stats,
)
from platform_context_graph.query.repositories.context_data import _fetch_infrastructure


class MockRecord:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data.get(key)

    def get(self, key, default=None):
        return self._data.get(key, default)


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


class FinderLike:
    def __init__(self, db_manager):
        self.db_manager = db_manager


def test_get_repository_context_returns_current_context_shape():
    repo_record = MockRecord(
        {
            "id": "repository:r_ab12cd34",
            "name": "my-api",
            "path": "/repos/my-api",
            "local_path": "/repos/my-api",
            "remote_url": "https://github.com/platformcontext/my-api",
            "repo_slug": "platformcontext/my-api",
            "has_remote": True,
        }
    )
    code_record = MockRecord({"functions": 10, "classes": 3})
    deps_record = MockRecord({"dependencies": []})
    dependents_record = MockRecord({"dependents": []})
    canonical_repo_id = _canonical_repository_id(
        remote_url="https://github.com/platformcontext/my-api",
        local_path="/repos/my-api",
    )

    db = make_mock_db(
        {
            "RETURN r.id as id, r.name as name, r.path as path": MockResult(
                records=[
                    {
                        "id": canonical_repo_id,
                        "name": "my-api",
                        "path": "/repos/my-api",
                        "local_path": "/repos/my-api",
                        "remote_url": "https://github.com/platformcontext/my-api",
                        "repo_slug": "platformcontext/my-api",
                        "has_remote": True,
                    }
                ]
            ),
            "split(f.name": MockResult(
                records=[
                    {"file": "main.py", "ext": "py"},
                    {"file": "utils.py", "ext": "py"},
                    {"file": "deploy.yaml", "ext": "yaml"},
                ]
            ),
            "count(DISTINCT fn)": MockResult(single_record=code_record),
            "fn.name IN": MockResult(records=[]),
            "K8sResource": MockResult(records=[]),
            "TerraformResource": MockResult(records=[]),
            "TerraformModule": MockResult(records=[]),
            "TerraformVariable": MockResult(records=[]),
            "TerraformOutput": MockResult(records=[]),
            "ArgoCDApplication": MockResult(records=[]),
            "ArgoCDApplicationSet": MockResult(records=[]),
            "CrossplaneXRD": MockResult(records=[]),
            "CrossplaneComposition": MockResult(records=[]),
            "CrossplaneClaim": MockResult(records=[]),
            "HelmChart": MockResult(records=[]),
            "HelmValues": MockResult(records=[]),
            "KustomizeOverlay": MockResult(records=[]),
            "TerragruntConfig": MockResult(records=[]),
            "type(rel) IN": MockResult(records=[]),
            "Tier": MockResult(single_record=None),
            "DEPENDS_ON]->(dep": MockResult(single_record=deps_record),
            "DEPENDS_ON]-(dep": MockResult(single_record=dependents_record),
        }
    )

    result = get_repository_context(db, repo_id=canonical_repo_id)

    assert result["repository"]["name"] == "my-api"
    assert result["repository"]["id"] == canonical_repo_id
    assert result["repository"]["local_path"] == "/repos/my-api"
    assert result["repository"]["repo_slug"] == "platformcontext/my-api"
    assert (
        result["repository"]["remote_url"]
        == "https://github.com/platformcontext/my-api"
    )
    assert result["repository"]["file_count"] == 3
    assert result["code"]["functions"] == 10
    assert result["code"]["classes"] == 3
    assert "python" in result["code"]["languages"]
    assert result["infrastructure"] == {}
    assert result["relationships"] == []
    assert result["ecosystem"] is None


def test_get_repository_stats_supports_repo_and_overall_modes():
    canonical_repo_id = _canonical_repository_id(
        remote_url="https://github.com/platformcontext/my-api",
        local_path="/repos/my-api",
    )
    db = make_mock_db(
        {
            "RETURN r.id as id, r.name as name, r.path as path": MockResult(
                records=[
                    {
                        "id": canonical_repo_id,
                        "name": "my-api",
                        "path": "/repos/my-api",
                        "local_path": "/repos/my-api",
                        "remote_url": "https://github.com/platformcontext/my-api",
                        "repo_slug": "platformcontext/my-api",
                        "has_remote": True,
                    }
                ]
            ),
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(f:File) RETURN count(f) as c": MockResult(
                single_record=MockRecord({"c": 3})
            ),
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(func:Function) RETURN count(func) as c": MockResult(
                single_record=MockRecord({"c": 7})
            ),
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(cls:Class) RETURN count(cls) as c": MockResult(
                single_record=MockRecord({"c": 2})
            ),
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(f:File)-[:IMPORTS]->(m:Module) RETURN count(DISTINCT m) as c": MockResult(
                single_record=MockRecord({"c": 5})
            ),
            "MATCH (r:Repository) RETURN count(r) as c": MockResult(
                single_record=MockRecord({"c": 4})
            ),
            "MATCH (f:File) RETURN count(f) as c": MockResult(
                single_record=MockRecord({"c": 20})
            ),
            "MATCH (func:Function) RETURN count(func) as c": MockResult(
                single_record=MockRecord({"c": 40})
            ),
            "MATCH (cls:Class) RETURN count(cls) as c": MockResult(
                single_record=MockRecord({"c": 8})
            ),
            "MATCH (m:Module) RETURN count(m) as c": MockResult(
                single_record=MockRecord({"c": 12})
            ),
        }
    )
    finder = FinderLike(db)

    scoped = get_repository_stats(finder, repo_id=canonical_repo_id)
    overall = get_repository_stats(finder, repo_id=None)

    assert scoped["success"] is True
    assert scoped["repository"]["id"] == canonical_repo_id
    assert scoped["repository"]["local_path"] == "/repos/my-api"
    assert scoped["stats"] == {"files": 3, "functions": 7, "classes": 2, "modules": 5}
    assert overall["success"] is True
    assert overall["stats"]["repositories"] == 4
    assert overall["stats"]["files"] == 20


def test_fetch_infrastructure_queries_reuse_matched_node_alias():
    class RecordingSession:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def run(self, query, **kwargs):
            self.queries.append(query)
            return MockResult(records=[])

    session = RecordingSession()

    assert (
        _fetch_infrastructure(
            session,
            {
                "id": "repository:r_ab12cd34",
                "path": "/repos/my-api",
                "local_path": "/repos/my-api",
            },
        )
        == {}
    )
    assert session.queries

    for query in session.queries:
        alias_match = re.search(r"-\[:CONTAINS\]->\((\w+):", query)
        assert alias_match is not None

        node_alias = alias_match.group(1)
        return_block = query.split("RETURN", 1)[1]
        return_aliases = set(re.findall(r"\b([A-Za-z_]\w*)\.", return_block))

        assert return_aliases <= {node_alias, "f"}


def test_get_repository_context_scopes_follow_up_queries_to_the_resolved_repository():
    primary_repo = {
        "id": "repository:r_primary123",
        "name": "payments-api",
        "path": "/repos/payments-api",
        "local_path": "/repos/payments-api",
        "remote_url": "https://github.com/platformcontext/payments-api",
        "repo_slug": "platformcontext/payments-api",
        "has_remote": True,
    }
    sibling_repo = {
        "id": "repository:r_worker456",
        "name": "payments-api-worker",
        "path": "/repos/payments-api-worker",
        "local_path": "/repos/payments-api-worker",
        "remote_url": "https://github.com/platformcontext/payments-api-worker",
        "repo_slug": "platformcontext/payments-api-worker",
        "has_remote": True,
    }

    class ContextSession:
        def run(self, query, **kwargs):
            if "MATCH (r:Repository)" in query and "RETURN r.id as id" in query:
                return MockResult(records=[primary_repo, sibling_repo])
            if "split(f.name" in query:
                if "r.id = $repo_id" in query:
                    return MockResult(records=[{"file": "payments.py", "ext": "py"}])
                return MockResult(
                    records=[
                        {"file": "payments.py", "ext": "py"},
                        {"file": "worker.py", "ext": "py"},
                    ]
                )
            if "count(DISTINCT fn)" in query:
                if "r.id = $repo_id" in query:
                    return MockResult(
                        single_record=MockRecord({"functions": 1, "classes": 0})
                    )
                return MockResult(
                    single_record=MockRecord({"functions": 2, "classes": 0})
                )
            if "fn.name IN" in query:
                if "r.id = $repo_id" in query:
                    return MockResult(
                        records=[{"name": "main", "file": "payments.py", "line": 1}]
                    )
                return MockResult(
                    records=[
                        {"name": "main", "file": "payments.py", "line": 1},
                        {"name": "main", "file": "worker.py", "line": 1},
                    ]
                )
            if "type(rel) IN" in query:
                if "r.id = $repo_id" in query:
                    return MockResult(records=[])
                return MockResult(
                    records=[
                        {
                            "type": "ROUTES_TO",
                            "from_name": "payments-api",
                            "from_kind": "Service",
                            "to_name": "payments-api-worker",
                            "to_kind": "Workload",
                        }
                    ]
                )
            if "K8sResource" in query:
                if "r.id = $repo_id" in query:
                    return MockResult(records=[])
                return MockResult(
                    records=[
                        {
                            "name": "payments-api-worker",
                            "kind": "Deployment",
                            "namespace": "payments",
                        }
                    ]
                )
            if "TerraformResource" in query:
                return MockResult(records=[])
            if "TerraformModule" in query:
                return MockResult(records=[])
            if "TerraformVariable" in query:
                return MockResult(records=[])
            if "TerraformOutput" in query:
                return MockResult(records=[])
            if "ArgoCDApplication" in query:
                return MockResult(records=[])
            if "ArgoCDApplicationSet" in query:
                return MockResult(records=[])
            if "CrossplaneXRD" in query:
                return MockResult(records=[])
            if "CrossplaneComposition" in query:
                return MockResult(records=[])
            if "CrossplaneClaim" in query:
                return MockResult(records=[])
            if "HelmChart" in query:
                return MockResult(records=[])
            if "HelmValues" in query:
                return MockResult(records=[])
            if "KustomizeOverlay" in query:
                return MockResult(records=[])
            if "TerragruntConfig" in query:
                return MockResult(records=[])
            if "Tier" in query:
                return MockResult(single_record=None)
            if "DEPENDS_ON]->(dep" in query:
                return MockResult(single_record=MockRecord({"dependencies": []}))
            if "DEPENDS_ON]-(dep" in query:
                return MockResult(single_record=MockRecord({"dependents": []}))
            return MockResult(records=[])

    session = ContextSession()
    db = MagicMock()
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    driver.session.return_value.__exit__.return_value = False
    db.get_driver.return_value = driver

    result = get_repository_context(db, repo_id="repository:r_primary123")

    assert result["repository"]["name"] == "payments-api"
    assert result["repository"]["file_count"] == 1
    assert result["code"]["functions"] == 1
    assert result["code"]["entry_points"] == [
        {"name": "main", "file": "payments.py", "line": 1}
    ]
    assert result["relationships"] == []
    assert result["infrastructure"] == {}
