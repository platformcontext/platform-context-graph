"""Shared fixtures for integration tests that require Neo4j.

Start the stack with: docker compose up -d
Run with:
    NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=testpassword \
    DATABASE_TYPE=neo4j uv run python -m pytest tests/integration/ -v
"""

import asyncio
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"
ECOSYSTEMS_DIR = FIXTURES / "ecosystems"
SAMPLE_PROJECTS_DIR = FIXTURES / "sample_projects"


def _neo4j_available() -> bool:
    return bool(os.getenv("NEO4J_URI"))


skip_no_neo4j = pytest.mark.skipif(
    not _neo4j_available(),
    reason="NEO4J_URI not set — start Neo4j with docker compose up -d",
)


@pytest.fixture(scope="session")
def db():
    """Get a Neo4j database manager for the full test session."""
    if not _neo4j_available():
        pytest.skip("NEO4J_URI not set")

    os.environ.setdefault("DATABASE_TYPE", "neo4j")
    from platform_context_graph.core import get_database_manager

    mgr = get_database_manager()
    yield mgr
    mgr.close_driver()


@pytest.fixture(scope="session")
def graph_builder(db):
    """Get a GraphBuilder wired to Neo4j."""
    from platform_context_graph.core.jobs import JobManager
    from platform_context_graph.tools.graph_builder import GraphBuilder

    loop = asyncio.new_event_loop()
    return GraphBuilder(db, JobManager(), loop)


@pytest.fixture(scope="session")
def indexed_ecosystems(db, graph_builder):
    """Index all ecosystem fixture repos and return the db manager.

    This fixture indexes every directory under tests/fixtures/ecosystems/
    so that integration tests can query the resulting graph.
    """
    driver = db.get_driver()
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

    for repo_dir in sorted(ECOSYSTEMS_DIR.iterdir()):
        if repo_dir.is_dir() and not repo_dir.name.startswith("."):
            asyncio.run(
                graph_builder.build_graph_from_path_async(
                    repo_dir, is_dependency=False
                )
            )

    yield db

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")


def cypher_single(db, query: str, **params) -> dict | None:
    """Run a Cypher query and return the single result record."""
    driver = db.get_driver()
    with driver.session() as session:
        return session.run(query, **params).single()


def cypher_all(db, query: str, **params) -> list[dict]:
    """Run a Cypher query and return all result records."""
    driver = db.get_driver()
    with driver.session() as session:
        return [dict(record) for record in session.run(query, **params)]
