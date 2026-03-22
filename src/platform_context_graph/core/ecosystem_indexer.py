"""Ecosystem-level indexer for multi-repo graph building.

Orchestrates indexing of all repos in an ecosystem manifest,
respecting tier dependencies, managing parallel indexing, and
supporting incremental updates via git change detection.
"""

import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ecosystem import (
    EcosystemManifest,
    EcosystemState,
    RepoIndexState,
    load_state,
    parse_manifest,
    resolve_repo_paths,
    save_state,
    topological_sort_tiers,
)
from .jobs import JobManager
from ..tools.graph_builder import GraphBuilder
from ..utils.debug_log import (
    error_logger,
    info_logger,
    warning_logger,
)


def _get_git_head_sha(repo_path: str) -> str:
    """Get the current HEAD commit SHA for a repo.

    Args:
        repo_path: Path to a git repository.

    Returns:
        40-character SHA string, or empty string on failure.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def _get_changed_files(repo_path: str, since_commit: str) -> dict[str, list[str]]:
    """Get files changed since a commit.

    Args:
        repo_path: Path to a git repository.
        since_commit: Git SHA to diff against HEAD.

    Returns:
        Dict with 'added', 'modified', 'deleted' lists of
        relative file paths.
    """
    changes: dict[str, list[str]] = {
        "added": [],
        "modified": [],
        "deleted": [],
    }

    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--name-status",
                since_commit,
                "HEAD",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return changes

        for line in result.stdout.strip().splitlines():
            parts = line.split("\t", 1)
            if len(parts) < 2:
                continue
            status = parts[0][0]
            filepath = parts[1]

            if status == "A":
                changes["added"].append(filepath)
            elif status in ("M", "R"):
                changes["modified"].append(filepath)
            elif status == "D":
                changes["deleted"].append(filepath)

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return changes


class EcosystemIndexer:
    """Orchestrates ecosystem-wide indexing.

    Manages the lifecycle of indexing all repos in a manifest:
    tier-ordered execution, parallel repo indexing within tiers,
    and state tracking for incremental updates.

    Args:
        graph_builder: GraphBuilder instance for indexing.
        job_manager: JobManager for tracking progress.
    """

    def __init__(
        self,
        graph_builder: GraphBuilder,
        job_manager: JobManager,
    ) -> None:
        """Initialize the ecosystem indexer."""
        self.graph_builder = graph_builder
        self.job_manager = job_manager

    async def index_ecosystem(
        self,
        manifest_path: str,
        base_path: str,
        force: bool = False,
        parallel: int = 4,
        clone_missing: bool = False,
    ) -> dict[str, Any]:
        """Index all repos in an ecosystem manifest.

        Args:
            manifest_path: Path to dependency-graph.yaml.
            base_path: Base dir where repos are cloned.
            force: If True, re-index all repos regardless
                of state.
            parallel: Max concurrent repo indexing.
            clone_missing: If True, clone missing repos.

        Returns:
            Summary dict with per-repo results.
        """
        manifest = parse_manifest(manifest_path)
        repo_paths = resolve_repo_paths(manifest, base_path)

        # Handle missing repos
        missing = [name for name, path in repo_paths.items() if not path]
        if missing and clone_missing:
            for repo_name in missing:
                repo = manifest.repos[repo_name]
                url = repo.github_url or (
                    f"https://github.com/{manifest.org}/{repo_name}.git"
                )
                clone_path = Path(base_path) / repo_name
                info_logger(f"Cloning {repo_name} -> {clone_path}")
                try:
                    subprocess.run(
                        ["gh", "repo", "clone", url, str(clone_path)],
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    if clone_path.is_dir():
                        repo_paths[repo_name] = str(clone_path)
                        manifest.repos[repo_name].local_path = str(clone_path)
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    warning_logger(f"Failed to clone {repo_name}: {e}")

        # Load persistent state
        state = load_state()
        state.manifest_path = manifest_path

        # Sort tiers for dependency-ordered indexing
        waves = topological_sort_tiers(manifest)

        results: dict[str, Any] = {
            "ecosystem": manifest.name,
            "total_repos": len(manifest.repos),
            "missing_repos": [n for n, p in repo_paths.items() if not p],
            "indexed": [],
            "skipped": [],
            "failed": [],
        }

        # Create ecosystem-level graph nodes
        self._create_ecosystem_nodes(manifest)

        semaphore = asyncio.Semaphore(parallel)

        for wave in waves:
            # Collect repos in this tier wave
            tier_repos = []
            for tier_name in wave:
                tier = manifest.tiers.get(tier_name)
                if tier:
                    tier_repos.extend(tier.repos)
                else:
                    # Repos assigned to tier but tier not in
                    # tiers section
                    for repo in manifest.repos.values():
                        if repo.tier == tier_name:
                            tier_repos.append(repo.name)

            # Index repos in parallel within each wave
            tasks = []
            for repo_name in tier_repos:
                local_path = repo_paths.get(repo_name, "")
                if not local_path:
                    results["skipped"].append(
                        {
                            "name": repo_name,
                            "reason": "not found locally",
                        }
                    )
                    continue

                # Skip if already indexed and not stale
                if not force:
                    repo_state = state.repos.get(repo_name)
                    if repo_state and repo_state.status == "indexed":
                        current_sha = _get_git_head_sha(local_path)
                        if (
                            current_sha
                            and current_sha == repo_state.last_indexed_commit
                        ):
                            results["skipped"].append(
                                {
                                    "name": repo_name,
                                    "reason": "up to date",
                                }
                            )
                            continue

                tasks.append(
                    self._index_repo(
                        repo_name,
                        local_path,
                        state,
                        semaphore,
                        results,
                    )
                )

            if tasks:
                await asyncio.gather(*tasks)

        save_state(state)
        return results

    async def update_ecosystem(
        self,
        manifest_path: str,
        base_path: str,
        parallel: int = 4,
    ) -> dict[str, Any]:
        """Incrementally update stale repos.

        Only re-indexes repos where HEAD has changed since
        last indexing.

        Args:
            manifest_path: Path to dependency-graph.yaml.
            base_path: Base dir where repos are cloned.
            parallel: Max concurrent repo indexing.

        Returns:
            Summary dict with per-repo results.
        """
        manifest = parse_manifest(manifest_path)
        repo_paths = resolve_repo_paths(manifest, base_path)
        state = load_state()

        results: dict[str, Any] = {
            "ecosystem": manifest.name,
            "updated": [],
            "skipped": [],
            "failed": [],
        }

        semaphore = asyncio.Semaphore(parallel)
        tasks = []

        for repo_name, local_path in repo_paths.items():
            if not local_path:
                continue

            repo_state = state.repos.get(repo_name)
            current_sha = _get_git_head_sha(local_path)

            if (
                repo_state
                and repo_state.status == "indexed"
                and current_sha == repo_state.last_indexed_commit
            ):
                results["skipped"].append(repo_name)
                continue

            tasks.append(
                self._index_repo(
                    repo_name,
                    local_path,
                    state,
                    semaphore,
                    results,
                )
            )

        if tasks:
            await asyncio.gather(*tasks)

        save_state(state)
        return results

    def get_status(self) -> dict[str, Any]:
        """Get current ecosystem indexing status.

        Returns:
            Dict with per-repo status info.
        """
        state = load_state()

        return {
            "manifest_path": state.manifest_path,
            "last_updated": state.last_updated,
            "repos": {
                name: {
                    "status": rs.status,
                    "last_commit": (
                        rs.last_indexed_commit[:8] if rs.last_indexed_commit else ""
                    ),
                    "last_indexed": rs.last_indexed_at,
                    "files": rs.file_count,
                    "error": rs.error,
                }
                for name, rs in state.repos.items()
            },
        }

    async def _index_repo(
        self,
        repo_name: str,
        local_path: str,
        state: EcosystemState,
        semaphore: asyncio.Semaphore,
        results: dict[str, Any],
    ) -> None:
        """Index a single repo with semaphore control."""
        async with semaphore:
            info_logger(f"Indexing repo: {repo_name}")
            job_id = self.job_manager.create_job(f"ecosystem-{repo_name}")

            try:
                await self.graph_builder.build_graph_from_path_async(
                    Path(local_path),
                    is_dependency=False,
                    job_id=job_id,
                )

                current_sha = _get_git_head_sha(local_path)
                now = datetime.now(timezone.utc).isoformat()

                driver = self.graph_builder.db_manager.get_driver()
                with driver.session() as session:
                    result = session.run(
                        "MATCH (r:Repository)-[:CONTAINS*]->(f:File) "
                        "WHERE r.name = $name RETURN count(f) as cnt",
                        name=repo_name,
                    ).single()
                    file_count = result["cnt"] if result else 0

                state.repos[repo_name] = RepoIndexState(
                    name=repo_name,
                    last_indexed_commit=current_sha,
                    status="indexed",
                    last_indexed_at=now,
                    file_count=file_count,
                )

                results.get("indexed", results.get("updated", [])).append(repo_name)
                info_logger(f"Indexed repo: {repo_name}")

            except Exception as e:
                error_logger(f"Failed to index {repo_name}: {e}")
                state.repos[repo_name] = RepoIndexState(
                    name=repo_name,
                    status="failed",
                    error=str(e),
                )
                results["failed"].append({"name": repo_name, "error": str(e)})

    def _create_ecosystem_nodes(self, manifest: EcosystemManifest) -> None:
        """Create Ecosystem and Tier nodes in the graph."""
        driver = self.graph_builder.driver

        with driver.session() as session:
            # Create Ecosystem node
            session.run(
                """
                MERGE (e:Ecosystem {name: $name})
                SET e.org = $org
                """,
                name=manifest.name,
                org=manifest.org,
            )

            # Create Tier nodes
            for tier_name, tier in manifest.tiers.items():
                session.run(
                    """
                    MERGE (t:Tier {name: $name})
                    SET t.risk_level = $risk_level
                    """,
                    name=tier_name,
                    risk_level=tier.risk_level,
                )

                # Tier belongs to Ecosystem
                session.run(
                    """
                    MATCH (e:Ecosystem {name: $eco_name})
                    MATCH (t:Tier {name: $tier_name})
                    MERGE (e)-[:CONTAINS]->(t)
                    """,
                    eco_name=manifest.name,
                    tier_name=tier_name,
                )

            # Create repo->tier relationships
            for repo in manifest.repos.values():
                if repo.tier:
                    session.run(
                        """
                        MATCH (t:Tier {name: $tier_name})
                        MATCH (r:Repository {name: $repo_name})
                        MERGE (t)-[:CONTAINS]->(r)
                        """,
                        tier_name=repo.tier,
                        repo_name=repo.name,
                    )

            # Create DEPENDS_ON between repos
            for repo in manifest.repos.values():
                for dep_name in repo.dependencies:
                    session.run(
                        """
                        MATCH (a:Repository {name: $from_name})
                        MATCH (b:Repository {name: $to_name})
                        MERGE (a)-[:DEPENDS_ON]->(b)
                        """,
                        from_name=repo.name,
                        to_name=dep_name,
                    )
