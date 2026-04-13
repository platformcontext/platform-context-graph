"""Guardrails against reintroducing deleted compatibility shim modules."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_deleted_compatibility_shim_paths_are_absent() -> None:
    """Phase 2 should not retain shim-only files that only preserved old imports."""

    forbidden_paths = (
        "src/platform_context_graph/tools/languages",
        "src/platform_context_graph/tools/parser_capabilities",
        "src/platform_context_graph/tools/package_resolver.py",
        "src/platform_context_graph/tools/dependency_catalog.py",
        "src/platform_context_graph/tools/parse_worker.py",
        "src/platform_context_graph/tools/repository_display.py",
        "src/platform_context_graph/tools/runtime_automation_families.py",
        "src/platform_context_graph/tools/runtime_platform_families.py",
        "src/platform_context_graph/tools/graph_builder_call_batches.py",
        "src/platform_context_graph/tools/graph_builder_call_otel.py",
        "src/platform_context_graph/tools/graph_builder_call_prefilter.py",
        "src/platform_context_graph/tools/graph_builder_call_relationships.py",
        "src/platform_context_graph/tools/graph_builder_directory_chain.py",
        "src/platform_context_graph/tools/graph_builder_entities.py",
        "src/platform_context_graph/tools/graph_builder_gitignore.py",
        "src/platform_context_graph/tools/graph_builder_indexing.py",
        "src/platform_context_graph/tools/graph_builder_indexing_discovery.py",
        "src/platform_context_graph/tools/graph_builder_indexing_execution.py",
        "src/platform_context_graph/tools/graph_builder_indexing_finalize.py",
        "src/platform_context_graph/tools/graph_builder_indexing_types.py",
        "src/platform_context_graph/tools/graph_builder_mutations.py",
        "src/platform_context_graph/tools/graph_builder_parsers.py",
        "src/platform_context_graph/tools/graph_builder_persistence_batch.py",
        "src/platform_context_graph/tools/graph_builder_raw_text.py",
        "src/platform_context_graph/tools/graph_builder_schema.py",
        "src/platform_context_graph/tools/graph_builder_scip.py",
        "src/platform_context_graph/tools/graph_builder_type_relationships.py",
        "src/platform_context_graph/tools/graph_builder_workload_batches.py",
        "src/platform_context_graph/tools/graph_builder_workload_dependency_support.py",
        "src/platform_context_graph/tools/graph_builder_workload_metrics.py",
        "src/platform_context_graph/tools/graph_builder_workload_projection.py",
        "src/platform_context_graph/tools/graph_builder_workloads.py",
        "src/platform_context_graph/tools/graph_builder_platforms.py",
        "src/platform_context_graph/tools/graph_builder_persistence_helpers.py",
        "src/platform_context_graph/tools/graph_builder_persistence_unwind.py",
        "src/platform_context_graph/tools/graph_builder_persistence_worker.py",
        "src/platform_context_graph/tools/scip_indexer.py",
        "src/platform_context_graph/tools/scip_parser.py",
        "src/platform_context_graph/tools/scip_support.py",
        "src/platform_context_graph/tools/cross_repo_linker_support.py",
        "src/platform_context_graph/parsers/scip",
        "src/platform_context_graph/parsers/languages/groovy_support.py",
        "src/platform_context_graph/parsers/languages/templated_detection.py",
        "src/platform_context_graph/parsers/languages/templated_detection_support.py",
        "src/platform_context_graph/collectors/git/parse_execution.py",
        "src/platform_context_graph/collectors/git/parse_worker.py",
        "src/platform_context_graph/indexing/coordinator.py",
        "src/platform_context_graph/indexing/coordinator_pipeline.py",
        "src/platform_context_graph/indexing/coordinator_async_commit.py",
        "src/platform_context_graph/indexing/parse_recovery.py",
    )

    existing = [
        relative_path
        for relative_path in forbidden_paths
        if (REPO_ROOT / relative_path).exists()
    ]

    assert existing == []
