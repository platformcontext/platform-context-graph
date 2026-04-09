"""Integration tests for repository subtree reset behavior."""

from __future__ import annotations

from pathlib import Path

from tests.integration.conftest import cypher_single, skip_no_neo4j

pytestmark = [skip_no_neo4j]


def test_reset_repository_subtree_executes_and_preserves_repository_node(
    db, graph_builder, tmp_path: Path
) -> None:
    """Reset should execute on Neo4j and clear repo-owned projection state."""

    repo_path = tmp_path / "api-node-fsbo"
    repo_id = f"repository:test-reset:{tmp_path.name}"
    repo_path_str = str(repo_path.resolve())
    workload_id = f"workload:test-reset:{tmp_path.name}"
    instance_id = f"instance:test-reset:{tmp_path.name}"
    marker_id = f"marker:test-reset:{tmp_path.name}"

    driver = db.get_driver()
    with driver.session() as session:
        session.run(
            """
            MATCH (r:Repository {id: $repo_id})
            OPTIONAL MATCH (r)-[:CONTAINS|REPO_CONTAINS*1..]->(owned_tree)
            WITH collect(DISTINCT r) + collect(DISTINCT owned_tree) AS owned_nodes
            UNWIND owned_nodes AS owned
            WITH DISTINCT owned
            WHERE owned IS NOT NULL
            DETACH DELETE owned
            """,
            repo_id=repo_id,
        )
        session.run(
            "MATCH (w:Workload {repo_id: $repo_id}) DETACH DELETE w",
            repo_id=repo_id,
        )
        session.run(
            "MATCH (i:WorkloadInstance {repo_id: $repo_id}) DETACH DELETE i",
            repo_id=repo_id,
        )
        session.run(
            "MATCH (m:Marker {id: $marker_id}) DETACH DELETE m",
            marker_id=marker_id,
        )
        session.run(
            """
            CREATE (r:Repository {
                id: $repo_id,
                path: $repo_path,
                local_path: $repo_path
            })
            CREATE (d:Directory {path: $dir_path})
            CREATE (f:File {path: $file_path})
            CREATE (w:Workload {id: $workload_id, repo_id: $repo_id})
            CREATE (i:WorkloadInstance {id: $instance_id, repo_id: $repo_id})
            CREATE (m:Marker {id: $marker_id})
            CREATE (r)-[:CONTAINS]->(d)
            CREATE (d)-[:CONTAINS]->(f)
            CREATE (r)-[:DEFINES]->(w)
            CREATE (i)-[:INSTANCE_OF]->(w)
            CREATE (r)-[:RELATES_TO]->(m)
            """,
            repo_id=repo_id,
            repo_path=repo_path_str,
            dir_path=f"{repo_path_str}/src",
            file_path=f"{repo_path_str}/src/app.py",
            workload_id=workload_id,
            instance_id=instance_id,
            marker_id=marker_id,
        )

    try:
        reset = graph_builder.reset_repository_subtree_in_graph(repo_id)

        assert reset is True
        assert (
            cypher_single(
                db,
                "MATCH (r:Repository {id: $repo_id}) RETURN count(r) AS count",
                repo_id=repo_id,
            )["count"]
            == 1
        )
        assert (
            cypher_single(
                db,
                "MATCH (:Repository {id: $repo_id})-[:CONTAINS|REPO_CONTAINS*1..]->() "
                "RETURN count(*) AS count",
                repo_id=repo_id,
            )["count"]
            == 0
        )
        assert (
            cypher_single(
                db,
                "MATCH (w:Workload {repo_id: $repo_id}) RETURN count(w) AS count",
                repo_id=repo_id,
            )["count"]
            == 0
        )
        assert (
            cypher_single(
                db,
                "MATCH (i:WorkloadInstance {repo_id: $repo_id}) RETURN count(i) AS count",
                repo_id=repo_id,
            )["count"]
            == 0
        )
        assert (
            cypher_single(
                db,
                "MATCH (:Repository {id: $repo_id})-[rel]-() RETURN count(rel) AS count",
                repo_id=repo_id,
            )["count"]
            == 0
        )
        assert (
            cypher_single(
                db,
                "MATCH (m:Marker {id: $marker_id}) RETURN count(m) AS count",
                marker_id=marker_id,
            )["count"]
            == 1
        )
    finally:
        with driver.session() as session:
            session.run(
                """
                MATCH (r:Repository {id: $repo_id})
                OPTIONAL MATCH (r)-[:CONTAINS|REPO_CONTAINS*1..]->(owned_tree)
                WITH collect(DISTINCT r) + collect(DISTINCT owned_tree) AS owned_nodes
                UNWIND owned_nodes AS owned
                WITH DISTINCT owned
                WHERE owned IS NOT NULL
                DETACH DELETE owned
                """,
                repo_id=repo_id,
            )
            session.run(
                "MATCH (w:Workload {repo_id: $repo_id}) DETACH DELETE w",
                repo_id=repo_id,
            )
            session.run(
                "MATCH (i:WorkloadInstance {repo_id: $repo_id}) DETACH DELETE i",
                repo_id=repo_id,
            )
            session.run(
                "MATCH (m:Marker {id: $marker_id}) DETACH DELETE m",
                marker_id=marker_id,
            )
