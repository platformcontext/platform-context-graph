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
        "src/platform_context_graph/parsers/languages/cpp.py",
        "src/platform_context_graph/parsers/languages/cpp_support.py",
        "src/platform_context_graph/parsers/languages/argocd.py",
        "src/platform_context_graph/parsers/languages/cloudformation.py",
        "src/platform_context_graph/parsers/languages/crossplane.py",
        "src/platform_context_graph/parsers/languages/dart.py",
        "src/platform_context_graph/parsers/languages/dart_support.py",
        "src/platform_context_graph/parsers/languages/dart_support_calls.py",
        "src/platform_context_graph/parsers/languages/dart_support_queries.py",
        "src/platform_context_graph/parsers/languages/haskell.py",
        "src/platform_context_graph/parsers/languages/haskell_support.py",
        "src/platform_context_graph/parsers/languages/helm.py",
        "src/platform_context_graph/parsers/languages/hcl_terraform_support.py",
        "src/platform_context_graph/parsers/languages/java.py",
        "src/platform_context_graph/parsers/languages/java_support.py",
        "src/platform_context_graph/parsers/languages/json_config.py",
        "src/platform_context_graph/parsers/languages/json_config_support.py",
        "src/platform_context_graph/parsers/languages/json_data_intelligence_support.py",
        "src/platform_context_graph/parsers/languages/kotlin.py",
        "src/platform_context_graph/parsers/languages/kotlin_support.py",
        "src/platform_context_graph/parsers/languages/kotlin_support_helpers.py",
        "src/platform_context_graph/parsers/languages/go.py",
        "src/platform_context_graph/parsers/languages/go_support.py",
        "src/platform_context_graph/parsers/languages/go_sql_support.py",
        "src/platform_context_graph/parsers/languages/ruby.py",
        "src/platform_context_graph/parsers/languages/ruby_support.py",
        "src/platform_context_graph/parsers/languages/sql.py",
        "src/platform_context_graph/parsers/languages/sql_support.py",
        "src/platform_context_graph/parsers/languages/sql_support_fallbacks.py",
        "src/platform_context_graph/parsers/languages/sql_support_migrations.py",
        "src/platform_context_graph/parsers/languages/sql_support_shared.py",
        "src/platform_context_graph/parsers/languages/sql_support_statements.py",
        "src/platform_context_graph/parsers/languages/swift.py",
        "src/platform_context_graph/parsers/languages/swift_support.py",
        "src/platform_context_graph/parsers/languages/runtime_dependencies.py",
        "src/platform_context_graph/parsers/languages/kustomize.py",
        "src/platform_context_graph/parsers/languages/templated_detection.py",
        "src/platform_context_graph/parsers/languages/templated_detection_support.py",
        "src/platform_context_graph/parsers/languages/yaml_infra_support.py",
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
