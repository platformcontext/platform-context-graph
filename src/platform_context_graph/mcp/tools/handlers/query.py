"""MCP handler functions for low-level query and visualization operations."""

import json
import os
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import READ_ACCESS
from neo4j.exceptions import CypherSyntaxError

from ....utils.debug_log import debug_log

_READ_ONLY_QUERY_ERROR = (
    "This tool only supports read-only queries. Prohibited clauses like CREATE, "
    "MERGE, DELETE, CALL, FOREACH, and LOAD CSV are not allowed."
)
_READ_ONLY_BLOCKED_PATTERNS = (
    r"\bCREATE\b",
    r"\bMERGE\b",
    r"\bDELETE\b",
    r"\bSET\b",
    r"\bREMOVE\b",
    r"\bDROP\b",
    r"\bFOREACH\b",
    r"\bLOAD\s+CSV\b",
    r"\bCALL\b",
)
_STRING_LITERAL_PATTERN = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''  # noqa: W605
_COMMENT_PATTERN = r"//.*?$|/\*.*?\*/"


def _query_is_read_only(cypher_query: str) -> bool:
    """Return `True` when a Cypher statement stays within the read-only contract."""

    query_without_strings = re.sub(_STRING_LITERAL_PATTERN, "", cypher_query)
    sanitized_query = re.sub(
        _COMMENT_PATTERN,
        "",
        query_without_strings,
        flags=re.MULTILINE | re.DOTALL,
    )
    return not any(
        re.search(pattern, sanitized_query, re.IGNORECASE)
        for pattern in _READ_ONLY_BLOCKED_PATTERNS
    )


def _read_only_query_error() -> dict[str, str]:
    """Return the standard error payload for blocked Cypher queries."""

    return {"error": _READ_ONLY_QUERY_ERROR}


def _open_read_session(db_manager):
    """Open the safest available read-oriented session for the active backend."""

    driver = db_manager.get_driver()
    backend_type = getattr(db_manager, "get_backend_type", lambda: "")().lower()
    if backend_type == "neo4j":
        return driver.session(default_access_mode=READ_ACCESS)
    return driver.session()


def _serialize_json_for_inline_script(value: object) -> str:
    """Serialize JSON safely for embedding inside an inline HTML script block."""

    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def execute_cypher_query(db_manager, **args: Any) -> dict[str, Any]:
    """
    Tool implementation for executing a read-only Cypher query.

    Important: Includes a safety check to prevent any database modification
    by disallowing keywords like CREATE, MERGE, DELETE, etc.
    """
    cypher_query = args.get("cypher_query")
    if not cypher_query:
        return {"error": "Cypher query cannot be empty."}

    if not _query_is_read_only(cypher_query):
        return _read_only_query_error()

    try:
        debug_log(f"Executing Cypher query: {cypher_query}")
        with _open_read_session(db_manager) as session:
            result = session.run(cypher_query)
            # Convert results to a list of dictionaries for clean JSON serialization.
            records = [record.data() for record in result]

            return {
                "success": True,
                "query": cypher_query,
                "record_count": len(records),
                "results": records,
            }

    except CypherSyntaxError as exc:
        debug_log(f"Cypher syntax error: {str(exc)}")
        return {
            "error": "Cypher syntax error.",
            "details": str(exc),
            "query": cypher_query,
        }
    except Exception as exc:
        debug_log(f"Error executing Cypher query: {str(exc)}")
        return {
            "error": "An unexpected error occurred while executing the query.",
            "details": str(exc),
        }


def visualize_graph_query(db_manager, **args: Any) -> dict[str, Any]:
    """Tool to generate a visualization URL (Neo4j URL or FalkorDB HTML file)."""
    cypher_query = args.get("cypher_query")
    if not cypher_query:
        return {"error": "Cypher query cannot be empty."}
    if not _query_is_read_only(cypher_query):
        return _read_only_query_error()

    # Check DB Type: FalkorDBManager vs DatabaseManager vs KuzuDBManager
    is_falkor = "FalkorDB" in db_manager.__class__.__name__
    is_kuzu = "KuzuDB" in db_manager.__class__.__name__

    if is_falkor or is_kuzu:
        try:
            data_nodes = []
            data_edges = []
            seen_nodes = set()

            with _open_read_session(db_manager) as session:
                result = session.run(cypher_query)
                for record in result:
                    # Iterate all values in the record to find Nodes and Relationships
                    # record is a FalkorDBRecord (dict-like), values() works
                    for val in record.values():
                        # Process Node
                        if hasattr(val, "labels") and hasattr(val, "id"):
                            nid = val.id
                            if nid not in seen_nodes:
                                seen_nodes.add(nid)
                                lbl = list(val.labels)[0] if val.labels else "Node"
                                props = getattr(val, "properties", {}) or {}
                                name = props.get("name", str(nid))

                                color = "#97c2fc"
                                if "Repository" in val.labels:
                                    color = "#ffb3ba"
                                elif "File" in val.labels:
                                    color = "#baffc9"
                                elif "Class" in val.labels:
                                    color = "#bae1ff"
                                elif "Function" in val.labels:
                                    color = "#ffffba"

                                data_nodes.append(
                                    {
                                        "id": nid,
                                        "label": name,
                                        "group": lbl,
                                        "title": str(props),
                                        "color": color,
                                    }
                                )

                        # Process Relationship
                        src = getattr(val, "src_node", None)
                        if src is None:
                            src = getattr(val, "start_node", None)

                        dst = getattr(val, "dest_node", None)
                        if dst is None:
                            dst = getattr(val, "end_node", None)

                        if src is not None and dst is not None:
                            lbl = getattr(val, "relation", None) or getattr(
                                val, "type", "REL"
                            )
                            data_edges.append(
                                {"from": src, "to": dst, "label": lbl, "arrows": "to"}
                            )

            nodes_json = _serialize_json_for_inline_script(data_nodes)
            edges_json = _serialize_json_for_inline_script(data_edges)

            # Generate HTML
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <title>PlatformContextGraph Visualization</title>
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style type="text/css">
    #mynetwork {{ width: 100%; height: 100vh; border: 1px solid lightgray; }}
  </style>
</head>
<body>
  <div id="mynetwork"></div>
  <script type="text/javascript">
    var nodes = new vis.DataSet({nodes_json});
    var edges = new vis.DataSet({edges_json});
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
            filename = f"codegraph_viz.html"
            out_path = Path(os.getcwd()) / filename
            with open(out_path, "w") as f:
                f.write(html_content)

            return {
                "success": True,
                "visualization_url": f"file://{out_path}",
                "message": f"Visualization generated at {out_path}. Open this file in your browser.",
            }

        except Exception as exc:
            debug_log(f"Error generating FalkorDB visualization: {str(exc)}")
            return {"error": f"Failed to generate visualization: {str(exc)}"}

    else:
        # Neo4j fallback
        try:
            encoded_query = urllib.parse.quote(cypher_query)
            visualization_url = (
                f"http://localhost:7474/browser/?cmd=edit&arg={encoded_query}"
            )

            return {
                "success": True,
                "visualization_url": visualization_url,
                "message": "Open the URL in your browser to visualize the graph query. The query will be pre-filled for editing.",
            }
        except Exception as exc:
            debug_log(f"Error generating visualization URL: {str(exc)}")
            return {"error": f"Failed to generate visualization URL: {str(exc)}"}
