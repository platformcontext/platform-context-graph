from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from platform_context_graph.graph.persistence.inheritance import (
    create_all_inheritance_links,
    create_inheritance_links,
)


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **kwargs: Any) -> None:
        self.calls.append((query, kwargs))


def test_create_inheritance_links_batches_resolved_edges_into_one_query(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "child.py"
    file_path.write_text("# inheritance fixture\n", encoding="utf-8")

    session = RecordingSession()
    file_data = {
        "path": str(file_path),
        "classes": [
            {"name": "LocalBase", "bases": []},
            {"name": "Child", "bases": ["BaseOne", "BaseTwo"]},
            {"name": "LocalChild", "bases": ["LocalBase"]},
            {"name": "IgnoredObject", "bases": ["object"]},
            {"name": "UnresolvedChild", "bases": ["MissingBase"]},
        ],
        "imports": [
            {"name": "pkg.base_one.BaseOne"},
            {"name": "pkg.base_two.BaseTwo"},
        ],
    }
    imports_map = {
        "BaseOne": [str(tmp_path / "pkg" / "base_one" / "BaseOne.py")],
        "BaseTwo": [str(tmp_path / "pkg" / "base_two" / "BaseTwo.py")],
    }

    create_inheritance_links(session, file_data, imports_map)

    assert len(session.calls) == 1
    query, params = session.calls[0]

    assert "UNWIND $rows AS row" in query
    assert params["rows"] == [
        {
            "child_name": "Child",
            "file_path": str(file_path.resolve()),
            "parent_name": "BaseOne",
            "resolved_parent_file_path": str(
                (tmp_path / "pkg" / "base_one" / "BaseOne.py").resolve()
            ),
        },
        {
            "child_name": "Child",
            "file_path": str(file_path.resolve()),
            "parent_name": "BaseTwo",
            "resolved_parent_file_path": str(
                (tmp_path / "pkg" / "base_two" / "BaseTwo.py").resolve()
            ),
        },
        {
            "child_name": "LocalChild",
            "file_path": str(file_path.resolve()),
            "parent_name": "LocalBase",
            "resolved_parent_file_path": str(file_path.resolve()),
        },
    ]


def test_create_inheritance_links_benchmark_fixture_records_query_count(
    tmp_path: Path,
    record_property,
) -> None:
    file_path = tmp_path / "benchmark_inheritance.py"
    file_path.write_text("# benchmark fixture\n", encoding="utf-8")

    class_count = 200
    base_count = 3
    base_names = [f"Base{index}" for index in range(base_count)]
    file_data = {
        "path": str(file_path),
        "classes": [
            {"name": f"Child{class_index}", "bases": list(base_names)}
            for class_index in range(class_count)
        ],
        "imports": [
            {"name": f"pkg.base_{index}.Base{index}"} for index in range(base_count)
        ],
    }
    imports_map = {
        base_name: [str(tmp_path / "pkg" / f"base_{index}" / f"{base_name}.py")]
        for index, base_name in enumerate(base_names)
    }
    session = RecordingSession()

    started = perf_counter()
    create_inheritance_links(session, file_data, imports_map)
    elapsed = perf_counter() - started

    assert len(session.calls) == 1
    _, params = session.calls[0]
    assert len(params["rows"]) == class_count * base_count

    record_property("resolved_inheritance_edges", class_count * base_count)
    record_property("query_count", len(session.calls))
    record_property("duration_seconds", round(elapsed, 6))


def test_create_all_inheritance_links_batches_rows_across_files() -> None:
    """Cross-file inheritance finalization should batch rows into one query."""

    session = RecordingSession()
    builder = type(
        "Builder",
        (),
        {
            "driver": type(
                "Driver", (), {"session": lambda self: _SessionContext(session)}
            )()
        },
    )()
    all_file_data = [
        {
            "path": "/tmp/repo/a.py",
            "classes": [{"name": "ChildA", "bases": ["BaseOne"]}],
            "imports": [{"name": "pkg.base_one.BaseOne"}],
        },
        {
            "path": "/tmp/repo/b.py",
            "classes": [{"name": "ChildB", "bases": ["BaseTwo"]}],
            "imports": [{"name": "pkg.base_two.BaseTwo"}],
        },
    ]
    imports_map = {
        "BaseOne": ["/tmp/repo/pkg/base_one/BaseOne.py"],
        "BaseTwo": ["/tmp/repo/pkg/base_two/BaseTwo.py"],
    }

    create_all_inheritance_links(builder, all_file_data, imports_map)

    assert len(session.calls) == 1
    query, params = session.calls[0]
    assert "UNWIND $rows AS row" in query
    assert len(params["rows"]) == 2


class _SessionContext:
    def __init__(self, session: RecordingSession) -> None:
        self._session = session

    def __enter__(self) -> RecordingSession:
        return self._session

    def __exit__(self, exc_type, exc, tb) -> None:
        return None
