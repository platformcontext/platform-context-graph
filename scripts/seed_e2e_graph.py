"""Seed a live Neo4j graph for Docker-backed prompt-contract e2e tests."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from platform_context_graph.core import get_database_manager
from platform_context_graph.core.jobs import JobManager
from platform_context_graph.tools.graph_builder import GraphBuilder

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ecosystems"
E2E_REPOSITORIES = [
    "argocd_comprehensive",
    "ansible_jenkins_automation",
    "helm_argocd_platform",
    "java_comprehensive",
    "kubernetes_comprehensive",
    "python_comprehensive",
    "terraform_comprehensive",
]


def main() -> None:
    """Clear the graph and index the e2e prompt-contract fixture subset."""

    db = get_database_manager()
    driver = db.get_driver()

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

    loop = asyncio.new_event_loop()
    graph_builder = GraphBuilder(db, JobManager(), loop)
    staged_root = Path(tempfile.mkdtemp(prefix="pcg-e2e-ecosystems-"))

    try:
        for repo_name in E2E_REPOSITORIES:
            repo_path = FIXTURES_ROOT / repo_name
            if not repo_path.exists():
                raise FileNotFoundError(f"Missing e2e fixture repository: {repo_path}")
            staged_path = staged_root / repo_name
            shutil.copytree(repo_path, staged_path)
            asyncio.run(
                graph_builder.build_graph_from_path_async(
                    staged_path,
                    is_dependency=False,
                )
            )
            print(f"Indexed {repo_name} from {staged_path}")
    finally:
        shutil.rmtree(staged_root, ignore_errors=True)
        loop.close()
        db.close_driver()


if __name__ == "__main__":
    main()
