"""Seed a live Neo4j graph for Docker-backed e2e fixture corpora."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from platform_context_graph.core import get_database_manager
from platform_context_graph.core.jobs import JobManager
from platform_context_graph.tools.graph_builder import GraphBuilder

_FIXTURE_SET_ENV = "PCG_E2E_FIXTURE_SET"
_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
_FIXTURE_SETS: dict[str, tuple[Path, tuple[str, ...]]] = {
    "prompt_contract": (
        _FIXTURE_ROOT / "ecosystems",
        (
            "argocd_comprehensive",
            "ansible_jenkins_automation",
            "helm_argocd_platform",
            "java_comprehensive",
            "kubernetes_comprehensive",
            "python_comprehensive",
            "terraform_comprehensive",
        ),
    ),
    "relationship_platform": (
        _FIXTURE_ROOT / "relationship_platform",
        (
            "delivery-argocd",
            "delivery-legacy-automation",
            "deployment-helm",
            "deployment-kustomize",
            "infra-modules-shared",
            "infra-network-foundation",
            "infra-runtime-legacy",
            "infra-runtime-modern",
            "service-edge-api",
            "service-worker-jobs",
        ),
    ),
}


def fixture_set_names() -> tuple[str, ...]:
    """Return the supported seed fixture-set names."""

    return tuple(sorted(_FIXTURE_SETS))


def resolve_fixture_set(
    fixture_set_name: str | None = None,
) -> tuple[Path, tuple[str, ...]]:
    """Resolve one configured fixture set into a root path and repo names."""

    requested_name = (
        fixture_set_name or os.getenv(_FIXTURE_SET_ENV) or "prompt_contract"
    ).strip()
    fixture_set = _FIXTURE_SETS.get(requested_name)
    if fixture_set is None:
        available = ", ".join(fixture_set_names())
        raise ValueError(
            f"Unknown fixture set '{requested_name}'. Available fixture sets: {available}"
        )
    return fixture_set


def main() -> None:
    """Clear the graph and index one selected e2e fixture subset."""

    fixtures_root, repositories = resolve_fixture_set()
    previous_ignore_hidden = os.getenv("IGNORE_HIDDEN_FILES")
    os.environ["IGNORE_HIDDEN_FILES"] = "false"

    db = get_database_manager()
    driver = db.get_driver()

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

    loop = asyncio.new_event_loop()
    graph_builder = GraphBuilder(db, JobManager(), loop)
    staged_root = Path(tempfile.mkdtemp(prefix="pcg-e2e-ecosystems-"))

    try:
        for repo_name in repositories:
            repo_path = fixtures_root / repo_name
            if not repo_path.exists():
                raise FileNotFoundError(f"Missing e2e fixture repository: {repo_path}")
            staged_path = staged_root / repo_name
            shutil.copytree(repo_path, staged_path)
            (staged_path / ".git").mkdir(parents=True, exist_ok=True)
            print(f"Staged {repo_name} at {staged_path}")
        asyncio.run(
            graph_builder.build_graph_from_path_async(
                staged_root,
                is_dependency=False,
            )
        )
        print(f"Indexed fixture set from {staged_root}")
    finally:
        shutil.rmtree(staged_root, ignore_errors=True)
        loop.close()
        db.close_driver()
        if previous_ignore_hidden is None:
            os.environ.pop("IGNORE_HIDDEN_FILES", None)
        else:
            os.environ["IGNORE_HIDDEN_FILES"] = previous_ignore_hidden


if __name__ == "__main__":
    main()
