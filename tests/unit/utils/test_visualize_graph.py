from __future__ import annotations

from pathlib import Path

from platform_context_graph.utils import visualize_graph


class _FakeQueryResult:
    def __init__(self, rows):
        self.result_set = rows


class _FakeGraph:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def query(self, query: str) -> _FakeQueryResult:
        if "RETURN id(n), labels(n)[0], n.name, n.path" in query:
            return _FakeQueryResult(
                [
                    (
                        1,
                        "Repository",
                        self._payload,
                        self._payload,
                    )
                ]
            )
        return _FakeQueryResult([(1, "CONTAINS", 2)])


class _FakeFalkorDB:
    def __init__(self, _db_path: str, payload: str) -> None:
        self._payload = payload

    def select_graph(self, _graph_name: str) -> _FakeGraph:
        return _FakeGraph(self._payload)


def test_generate_visualization_escapes_inline_script_payloads(
    monkeypatch,
    tmp_path: Path,
) -> None:
    payload = "</script><script>alert(1)</script>"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(visualize_graph, "get_app_home", lambda: tmp_path)
    monkeypatch.setattr(visualize_graph.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(
        visualize_graph,
        "FalkorDB",
        lambda db_path: _FakeFalkorDB(db_path, payload),
    )

    visualize_graph.generate_visualization()

    html = (tmp_path / "graph_viz.html").read_text(encoding="utf-8")

    assert payload not in html
    assert r"<\/script><script>alert(1)<\/script>" in html
    assert "&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in html
