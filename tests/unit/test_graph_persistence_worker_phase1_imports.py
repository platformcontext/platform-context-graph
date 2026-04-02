"""Phase 1 import compatibility tests for graph persistence worker helpers."""

from platform_context_graph.graph.persistence.worker import (
    commit_batch_in_process as new_commit_batch_in_process,
)
from platform_context_graph.graph.persistence.worker import (
    get_commit_worker_connection_params as new_get_commit_worker_connection_params,
)
from platform_context_graph.tools.graph_builder_persistence_worker import (
    commit_batch_in_process as legacy_commit_batch_in_process,
)
from platform_context_graph.tools.graph_builder_persistence_worker import (
    get_commit_worker_connection_params as legacy_get_commit_worker_connection_params,
)


def test_graph_persistence_worker_moves_to_graph_package() -> None:
    """Expose worker helpers from the graph persistence package."""
    assert new_commit_batch_in_process.__module__ == (
        "platform_context_graph.graph.persistence.worker"
    )


def test_legacy_graph_persistence_worker_imports_reexport_new_api() -> None:
    """Keep legacy worker imports working during Phase 1."""
    assert legacy_commit_batch_in_process is new_commit_batch_in_process
    assert (
        legacy_get_commit_worker_connection_params
        is new_get_commit_worker_connection_params
    )
