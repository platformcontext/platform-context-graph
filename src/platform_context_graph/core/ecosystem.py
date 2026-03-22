"""Ecosystem manifest parser for multi-repo dependency graphs.

Parses a dependency-graph.yaml manifest into structured dataclasses
representing the ecosystem's repos, tiers, and dependencies. Also
manages persistent indexing state for incremental updates.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..utils.debug_log import warning_logger
from ..paths import get_app_home

# Persistent state directory
_STATE_DIR = get_app_home()
_STATE_FILE = _STATE_DIR / "ecosystem-state.json"


@dataclass
class EcosystemRepo:
    """Represents a single repository in the ecosystem.

    Attributes:
        name: Repository name (e.g., 'iac-eks-argocd').
        tier: Tier this repo belongs to (e.g., 'core').
        role: Short description of the repo's purpose.
        github_url: Full GitHub URL for cloning.
        key_docs: List of important doc paths within the repo.
        dependencies: List of repo names this repo depends on.
        local_path: Resolved local filesystem path (set at runtime).
    """

    name: str
    tier: str
    role: str = ""
    github_url: str = ""
    key_docs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    local_path: str = ""


@dataclass
class EcosystemTier:
    """Represents a tier grouping of repos.

    Attributes:
        name: Tier name (e.g., 'core', 'infrastructure').
        risk_level: Risk classification (high, medium, low).
        repos: List of repo names in this tier.
        depends_on: List of tier names this tier depends on.
    """

    name: str
    risk_level: str = "medium"
    repos: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class EcosystemManifest:
    """Parsed ecosystem manifest.

    Attributes:
        name: Ecosystem name.
        org: GitHub organization.
        tiers: Map of tier name to EcosystemTier.
        repos: Map of repo name to EcosystemRepo.
        raw: Original parsed YAML dict.
    """

    name: str
    org: str
    tiers: dict[str, EcosystemTier] = field(default_factory=dict)
    repos: dict[str, EcosystemRepo] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class RepoIndexState:
    """Persistent indexing state for a single repo.

    Attributes:
        name: Repository name.
        last_indexed_commit: Git SHA of last indexed commit.
        status: Current status (indexed, stale, failed, pending).
        last_indexed_at: ISO timestamp of last indexing.
        file_count: Number of files indexed.
        error: Last error message if status is 'failed'.
    """

    name: str
    last_indexed_commit: str = ""
    status: str = "pending"
    last_indexed_at: str = ""
    file_count: int = 0
    error: str = ""


@dataclass
class EcosystemState:
    """Persistent indexing state for the full ecosystem.

    Attributes:
        manifest_path: Path to the manifest file.
        repos: Map of repo name to RepoIndexState.
        last_updated: ISO timestamp of last state update.
    """

    manifest_path: str = ""
    repos: dict[str, RepoIndexState] = field(default_factory=dict)
    last_updated: str = ""


def parse_manifest(manifest_path: str) -> EcosystemManifest:
    """Parse a dependency-graph.yaml ecosystem manifest.

    Args:
        manifest_path: Absolute path to the manifest file.

    Returns:
        Parsed EcosystemManifest with all repos and tiers.

    Raises:
        FileNotFoundError: If the manifest file doesn't exist.
        ValueError: If the manifest has invalid structure.
    """
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Ecosystem manifest not found: {manifest_path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError("Ecosystem manifest must be a YAML mapping")

    ecosystem_name = raw.get("name", path.stem)
    org = raw.get("org", raw.get("organization", ""))

    manifest = EcosystemManifest(name=ecosystem_name, org=org, raw=raw)

    # Parse tiers
    tiers_data = raw.get("tiers", {})
    if isinstance(tiers_data, dict):
        for tier_name, tier_info in tiers_data.items():
            if not isinstance(tier_info, dict):
                continue
            tier = EcosystemTier(
                name=tier_name,
                risk_level=tier_info.get("risk_level", "medium"),
                repos=tier_info.get("repos", []),
                depends_on=tier_info.get("depends_on", []),
            )
            manifest.tiers[tier_name] = tier

    # Parse repos
    repos_data = raw.get("repos", raw.get("repositories", {}))
    if isinstance(repos_data, dict):
        for repo_name, repo_info in repos_data.items():
            if not isinstance(repo_info, dict):
                continue
            github_url = repo_info.get("github_url", repo_info.get("github", ""))
            repo = EcosystemRepo(
                name=repo_name,
                tier=repo_info.get("tier", ""),
                role=repo_info.get("role", ""),
                github_url=github_url,
                key_docs=repo_info.get("key_docs", []),
                dependencies=repo_info.get("dependencies", []),
            )
            manifest.repos[repo_name] = repo
    elif isinstance(repos_data, list):
        for repo_info in repos_data:
            if not isinstance(repo_info, dict):
                continue
            repo_name = repo_info.get("name", "")
            if not repo_name:
                continue
            github_url = repo_info.get("github_url", repo_info.get("github", ""))
            repo = EcosystemRepo(
                name=repo_name,
                tier=repo_info.get("tier", ""),
                role=repo_info.get("role", ""),
                github_url=github_url,
                key_docs=repo_info.get("key_docs", []),
                dependencies=repo_info.get("dependencies", []),
            )
            manifest.repos[repo_name] = repo

    # Auto-infer tiers from repo entries when no explicit tiers section
    if not manifest.tiers:
        inferred_tiers: dict[str, list[str]] = {}
        for repo in manifest.repos.values():
            if repo.tier:
                if repo.tier not in inferred_tiers:
                    inferred_tiers[repo.tier] = []
                inferred_tiers[repo.tier].append(repo.name)

        for tier_name, tier_repos in inferred_tiers.items():
            manifest.tiers[tier_name] = EcosystemTier(
                name=tier_name,
                repos=tier_repos,
            )

    return manifest


def resolve_repo_paths(manifest: EcosystemManifest, base_path: str) -> dict[str, str]:
    """Resolve local filesystem paths for each repo.

    Checks common directory structures:
    - {base_path}/{repo_name}
    - {base_path}/{org}/{repo_name}

    Args:
        manifest: Parsed ecosystem manifest.
        base_path: Base directory where repos are cloned.

    Returns:
        Dict mapping repo name to resolved local path.
        Missing repos have empty string values.
    """
    base = Path(base_path).expanduser().resolve()
    paths: dict[str, str] = {}

    for repo_name in manifest.repos:
        # Try direct path
        candidate = base / repo_name
        if candidate.is_dir():
            paths[repo_name] = str(candidate)
            manifest.repos[repo_name].local_path = str(candidate)
            continue

        # Try org/repo_name
        if manifest.org:
            candidate = base / manifest.org / repo_name
            if candidate.is_dir():
                paths[repo_name] = str(candidate)
                manifest.repos[repo_name].local_path = str(candidate)
                continue

        paths[repo_name] = ""

    return paths


def topological_sort_tiers(
    manifest: EcosystemManifest,
) -> list[list[str]]:
    """Sort tiers into dependency-ordered waves.

    Returns a list of waves, where each wave is a list of
    tier names that can be processed in parallel.

    Args:
        manifest: Parsed ecosystem manifest.

    Returns:
        List of waves (lists of tier names), ordered by
        dependency.
    """
    # Build dependency graph
    tier_deps: dict[str, set[str]] = {}
    all_tiers = set(manifest.tiers.keys())

    for tier_name, tier in manifest.tiers.items():
        deps = set(tier.depends_on) & all_tiers
        tier_deps[tier_name] = deps

    # Add any tiers from repos not explicitly in tiers section
    for repo in manifest.repos.values():
        if repo.tier and repo.tier not in tier_deps:
            tier_deps[repo.tier] = set()
            all_tiers.add(repo.tier)

    waves: list[list[str]] = []
    processed: set[str] = set()

    while len(processed) < len(all_tiers):
        # Find tiers whose dependencies are all processed
        wave = [
            t for t in all_tiers - processed if tier_deps.get(t, set()) <= processed
        ]

        if not wave:
            # Circular dependency — add remaining tiers
            wave = list(all_tiers - processed)
            warning_logger(
                f"Circular tier dependencies detected, adding remaining: {wave}"
            )

        waves.append(sorted(wave))
        processed.update(wave)

    return waves


# --- State persistence ---


def load_state() -> EcosystemState:
    """Load persistent ecosystem indexing state.

    Returns:
        EcosystemState loaded from disk, or empty state
        if no state file exists.
    """
    if not _STATE_FILE.exists():
        return EcosystemState()

    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)

        state = EcosystemState(
            manifest_path=data.get("manifest_path", ""),
            last_updated=data.get("last_updated", ""),
        )

        for name, repo_data in data.get("repos", {}).items():
            state.repos[name] = RepoIndexState(
                name=name,
                last_indexed_commit=repo_data.get("last_indexed_commit", ""),
                status=repo_data.get("status", "pending"),
                last_indexed_at=repo_data.get("last_indexed_at", ""),
                file_count=repo_data.get("file_count", 0),
                error=repo_data.get("error", ""),
            )

        return state
    except (json.JSONDecodeError, KeyError) as e:
        warning_logger(f"Error loading ecosystem state: {e}")
        return EcosystemState()


def save_state(state: EcosystemState) -> None:
    """Save ecosystem indexing state to disk.

    Args:
        state: Current ecosystem state to persist.
    """
    _STATE_DIR.mkdir(parents=True, exist_ok=True)

    state.last_updated = datetime.now(timezone.utc).isoformat()

    data: dict[str, Any] = {
        "manifest_path": state.manifest_path,
        "last_updated": state.last_updated,
        "repos": {},
    }

    for name, repo_state in state.repos.items():
        data["repos"][name] = asdict(repo_state)

    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
