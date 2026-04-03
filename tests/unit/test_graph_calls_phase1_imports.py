"""Phase 1 import compatibility tests for CALLS relationship helpers."""

from platform_context_graph.graph.persistence.call_batches import (
    contextual_call_batch_queries as new_contextual_call_batch_queries,
)
from platform_context_graph.graph.persistence.call_otel import (
    emit_call_resolution_otel_metrics as new_emit_call_resolution_otel_metrics,
)
from platform_context_graph.graph.persistence.call_prefilter import (
    compatible_languages as new_compatible_languages,
)
from platform_context_graph.graph.persistence.calls import (
    create_all_function_calls as new_create_all_function_calls,
)
from platform_context_graph.graph.persistence.calls import (
    create_function_calls as new_create_function_calls,
)
from platform_context_graph.tools.graph_builder_call_batches import (
    contextual_call_batch_queries as legacy_contextual_call_batch_queries,
)
from platform_context_graph.tools.graph_builder_call_otel import (
    emit_call_resolution_otel_metrics as legacy_emit_call_resolution_otel_metrics,
)
from platform_context_graph.tools.graph_builder_call_prefilter import (
    compatible_languages as legacy_compatible_languages,
)
from platform_context_graph.tools.graph_builder_call_relationships import (
    create_all_function_calls as legacy_create_all_function_calls,
)
from platform_context_graph.tools.graph_builder_call_relationships import (
    create_function_calls as legacy_create_function_calls,
)


def test_call_relationship_helpers_move_to_graph_persistence_package() -> None:
    """Expose CALLS helpers from canonical graph persistence modules."""
    assert new_create_function_calls.__module__ == (
        "platform_context_graph.graph.persistence.calls"
    )
    assert new_create_all_function_calls.__module__ == (
        "platform_context_graph.graph.persistence.calls"
    )
    assert new_contextual_call_batch_queries.__module__ == (
        "platform_context_graph.graph.persistence.call_batches"
    )
    assert new_compatible_languages.__module__ == (
        "platform_context_graph.graph.persistence.call_prefilter"
    )
    assert new_emit_call_resolution_otel_metrics.__module__ == (
        "platform_context_graph.graph.persistence.call_otel"
    )


def test_legacy_call_relationship_imports_reexport_canonical_api() -> None:
    """Keep legacy CALLS imports working during Phase 1."""
    assert legacy_create_function_calls is new_create_function_calls
    assert legacy_create_all_function_calls is new_create_all_function_calls
    assert legacy_contextual_call_batch_queries is new_contextual_call_batch_queries
    assert legacy_compatible_languages is new_compatible_languages
    assert (
        legacy_emit_call_resolution_otel_metrics
        is new_emit_call_resolution_otel_metrics
    )
