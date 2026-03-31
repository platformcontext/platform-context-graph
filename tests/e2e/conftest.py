from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on non-POSIX platforms
    fcntl = None

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SEED_SCRIPT = _REPO_ROOT / "scripts" / "seed_e2e_graph.py"
_GRAPH_LOCK = Path(tempfile.gettempdir()) / "pcg-e2e-graph.lock"


@pytest.fixture
def exclusive_e2e_graph() -> None:
    """Serialize graph-mutating e2e tests across xdist workers."""

    if fcntl is None:
        pytest.skip("e2e graph locking requires POSIX file locking support")
    _GRAPH_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with _GRAPH_LOCK.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@pytest.fixture
def seeded_e2e_graph(exclusive_e2e_graph: None) -> None:
    """Re-seed the live graph with the default prompt-contract fixture corpus."""

    _run_seed_script()
    yield


@pytest.fixture
def seeded_relationship_platform_graph(exclusive_e2e_graph: None) -> None:
    """Re-seed the live graph with the synthetic relationship-platform corpus."""

    _run_seed_script(fixture_set="relationship_platform")
    yield


def _run_seed_script(*, fixture_set: str | None = None) -> None:
    """Run the shared e2e seed script for one selected fixture set."""

    env = os.environ.copy()
    pythonpath_parts = [str(_REPO_ROOT / "src"), str(_REPO_ROOT)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = ":".join(pythonpath_parts)
    if fixture_set:
        env["PCG_E2E_FIXTURE_SET"] = fixture_set
    completed = subprocess.run(
        [sys.executable, str(_SEED_SCRIPT)],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to seed the e2e graph fixtures.\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
