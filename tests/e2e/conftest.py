from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SEED_SCRIPT = _REPO_ROOT / "scripts" / "seed_e2e_graph.py"
_GRAPH_LOCK = Path(tempfile.gettempdir()) / "pcg-e2e-graph.lock"


@pytest.fixture
def exclusive_e2e_graph() -> None:
    """Serialize graph-mutating e2e tests across xdist workers."""

    _GRAPH_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with _GRAPH_LOCK.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@pytest.fixture
def seeded_e2e_graph(exclusive_e2e_graph: None) -> None:
    """Re-seed the live graph with the prompt-contract fixture corpus."""

    env = os.environ.copy()
    pythonpath_parts = [str(_REPO_ROOT / "src"), str(_REPO_ROOT)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = ":".join(pythonpath_parts)
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
    yield
