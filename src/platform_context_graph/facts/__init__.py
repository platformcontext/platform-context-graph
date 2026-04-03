"""Facts-first storage, queue, and runtime contracts."""

from .state import (
    facts_first_indexing_enabled,
    facts_runtime_ready,
    get_fact_store,
    get_fact_work_queue,
    git_facts_first_enabled,
    reset_fact_runtime_for_tests,
    reset_facts_runtime_for_tests,
)

__all__ = [
    "facts_first_indexing_enabled",
    "facts_runtime_ready",
    "get_fact_store",
    "get_fact_work_queue",
    "git_facts_first_enabled",
    "reset_fact_runtime_for_tests",
    "reset_facts_runtime_for_tests",
]
