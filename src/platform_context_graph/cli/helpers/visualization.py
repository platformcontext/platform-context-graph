"""Visualization-oriented CLI helper implementations."""

from __future__ import annotations

import json
import threading
import time
import traceback
import urllib.parse
import uuid
import webbrowser
from pathlib import Path
from typing import Any


def _api():
    """Return the canonical ``cli_helpers`` module for shared state."""
    from .. import cli_helpers as api

    return api


def _node_color_for_label(label: str) -> str:
    """Return the legacy color used for a node label.

    Args:
        label: Graph label or entity type.

    Returns:
        A hex color string used by the legacy fallback visualizations.
    """
    mapping = {
        "Repository": "#ffb3ba",
        "File": "#baffc9",
        "Class": "#bae1ff",
        "Function": "#ffffba",
        "Package": "#ffdfba",
        "Module": "#ffdfba",
    }
    return mapping.get(label, "#97c2fc")


def _write_legacy_visualization(
    data_nodes: list[dict[str, Any]],
    data_edges: list[dict[str, Any]],
    title: str,
) -> None:
    """Write the fallback HTML visualization and open it in a browser.

    Args:
        data_nodes: Serialized vis-network node payloads.
        data_edges: Serialized vis-network edge payloads.
        title: Browser title for the generated visualization.
    """
    api = _api()
    filename = "codegraph_viz.html"
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <title>{title}</title>
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style type="text/css">
    #mynetwork {{
      width: 100%;
      height: 100vh;
      border: 1px solid lightgray;
    }}
  </style>
</head>
<body>
  <div id="mynetwork"></div>
  <script type="text/javascript">
    var nodes = new vis.DataSet({json.dumps(data_nodes)});
    var edges = new vis.DataSet({json.dumps(data_edges)});
    var container = document.getElementById('mynetwork');
    var data = {{ nodes: nodes, edges: edges }};
    var options = {{
        nodes: {{ shape: 'dot', size: 16 }},
        physics: {{ stabilization: false }},
        layout: {{ improvedLayout: false }}
    }};
    var network = new vis.Network(container, data, options);
  </script>
</body>
</html>
"""
    out_path = Path(filename).resolve()
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(html_content)

    api.console.print(f"[green]Visualization generated at:[/green] {out_path}")
    api.console.print("Opening in default browser...")
    webbrowser.open(f"file://{out_path}")


def visualize_helper(repo_path: str | None = None, port: int = 8000) -> None:
    """Launch the packaged Playground visualizer UI.

    Args:
        repo_path: Optional repository path to preselect in the UI.
        port: Local HTTP port for the visualizer backend.
    """
    api = _api()
    services = api._initialize_services()
    if not all(services):
        return

    db_manager, _, _ = services
    if db_manager is None:
        return
    from ...viz.server import run_server, set_db_manager

    set_db_manager(db_manager)
    static_dir = Path(__file__).resolve().parents[2] / "viz" / "dist"
    if not static_dir.exists():
        api.console.print(
            "[yellow]Warning: Visualizer UI assets not found in package.[/yellow]"
        )
        api.console.print(
            "[dim]Expected packaged assets under src/platform_context_graph/viz/dist.[/dim]"
        )
        db_manager.close_driver()
        return

    backend_url = f"http://localhost:{port}"
    params: dict[str, str] = {"backend": backend_url}
    if repo_path:
        params["repo_path"] = str(Path(repo_path).resolve())

    query_string = urllib.parse.urlencode(params)
    visualization_url = f"{backend_url}/playground?{query_string}"

    api.console.print(f"[green]Starting visualizer server on {backend_url}...[/green]")
    api.console.print(f"[cyan]Opening Playground UI:[/cyan] {visualization_url}")

    def open_browser() -> None:
        """Open the browser once the local server has had time to start."""
        time.sleep(1.5)
        webbrowser.open(visualization_url)

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        run_server(host="127.0.0.1", port=port, static_dir=str(static_dir))
    except Exception as exc:
        api.console.print(
            "[bold red]An error occurred while running the server:[/bold red] " f"{exc}"
        )
    finally:
        db_manager.close_driver()


def _visualize_falkordb(db_manager) -> None:
    """Render a static visualization from FalkorDB records.

    Args:
        db_manager: Database manager with a FalkorDB-compatible driver.
    """
    api = _api()
    api.console.print(
        "[dim]Generating FalkorDB visualization (showing up to 500 relationships)...[/dim]"
    )
    try:
        data_nodes: list[dict[str, Any]] = []
        data_edges: list[dict[str, Any]] = []
        seen_nodes: set[Any] = set()

        with db_manager.get_driver().session() as session:
            result = session.run("MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 500")

            for record in result:
                n = record["n"]
                r = record["r"]
                m = record["m"]

                def process_node(node) -> Any:
                    """Collect a FalkorDB node into the vis-network payload."""
                    nid = getattr(node, "id", -1)
                    labels = getattr(node, "labels", [])
                    label = list(labels)[0] if labels else "Node"
                    props = getattr(node, "properties", {})
                    name = props.get("name", str(nid))

                    if nid not in seen_nodes:
                        seen_nodes.add(nid)
                        data_nodes.append(
                            {
                                "id": nid,
                                "label": name,
                                "group": label,
                                "title": str(props),
                                "color": _node_color_for_label(label),
                            }
                        )
                    return nid

                source_id = process_node(n)
                target_id = process_node(m)
                edge_type = getattr(r, "relation", "") or getattr(r, "type", "REL")
                data_edges.append(
                    {
                        "from": source_id,
                        "to": target_id,
                        "label": edge_type,
                        "arrows": "to",
                    }
                )

        _write_legacy_visualization(
            data_nodes,
            data_edges,
            "PlatformContextGraph Visualization",
        )
    except Exception as exc:
        api.console.print(f"[bold red]Visualization failed:[/bold red] {exc}")
        traceback.print_exc()
    finally:
        db_manager.close_driver()


def _visualize_kuzudb(db_manager) -> None:
    """Render a static visualization from KùzuDB records.

    Args:
        db_manager: Database manager with a Kùzu-compatible driver.
    """
    api = _api()
    api.console.print(
        "[dim]Generating KùzuDB visualization (showing up to 500 relationships)...[/dim]"
    )
    try:
        data_nodes: list[dict[str, Any]] = []
        data_edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()

        with db_manager.get_driver().session() as session:
            result = session.run("MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 500")

            def process_node(node) -> str:
                """Collect a Kùzu node into the vis-network payload."""
                uid = None
                label = "Node"
                props = {}

                if hasattr(node, "properties"):
                    props = node.properties or {}
                    if hasattr(node, "labels") and node.labels:
                        label = node.labels[0]
                    if hasattr(node, "id"):
                        uid = str(node.id)
                elif isinstance(node, dict):
                    if "_id" in node:
                        uid = f"{node['_id']['table']}_{node['_id']['offset']}"
                    label = node.get("_label", "Node")
                    props = {
                        key: value
                        for key, value in node.items()
                        if not key.startswith("_")
                    }

                if not uid:
                    uid = str(uuid.uuid4())

                if uid not in seen_nodes:
                    seen_nodes.add(uid)
                    data_nodes.append(
                        {
                            "id": uid,
                            "label": props.get("name", str(uid)),
                            "group": label,
                            "title": str(props),
                            "color": _node_color_for_label(label),
                        }
                    )
                return uid

            for record in result:
                source_id = process_node(record["n"])
                target_id = process_node(record["m"])
                relationship = record["r"]
                edge_type = "REL"
                if hasattr(relationship, "type"):
                    edge_type = relationship.type
                elif isinstance(relationship, dict):
                    edge_type = relationship.get("_label", "REL")
                elif hasattr(relationship, "label"):
                    edge_type = relationship.label

                data_edges.append(
                    {
                        "from": source_id,
                        "to": target_id,
                        "label": edge_type,
                        "arrows": "to",
                    }
                )

        _write_legacy_visualization(
            data_nodes,
            data_edges,
            "PlatformContextGraph KùzuDB Visualization",
        )
    except Exception as exc:
        api.console.print(f"[bold red]Visualization failed:[/bold red] {exc}")
        traceback.print_exc()
    finally:
        db_manager.close_driver()
