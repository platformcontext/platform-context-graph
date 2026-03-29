"""Schema creation helpers for ``GraphBuilder`` storage initialization."""

from __future__ import annotations

from typing import Any

from ..content.ingest import CONTENT_ENTITY_LABELS
from platform_context_graph.core.database import (
    GraphStoreCapabilities,
    graph_store_capabilities_for_backend,
)

_UID_SCHEMA_LABELS = tuple(sorted(CONTENT_ENTITY_LABELS))
_UID_CONSTRAINT_STATEMENTS = tuple(
    (
        "CREATE CONSTRAINT "
        f"{label.lower()}_uid_unique "
        f"IF NOT EXISTS FOR (n:{label}) REQUIRE n.uid IS UNIQUE"
    )
    for label in _UID_SCHEMA_LABELS
)

_SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT repository_id IF NOT EXISTS FOR (r:Repository) REQUIRE r.id IS UNIQUE",
    "CREATE CONSTRAINT repository_path IF NOT EXISTS FOR (r:Repository) REQUIRE r.path IS UNIQUE",
    "CREATE CONSTRAINT path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE",
    "CREATE CONSTRAINT directory_path IF NOT EXISTS FOR (d:Directory) REQUIRE d.path IS UNIQUE",
    "CREATE CONSTRAINT function_unique IF NOT EXISTS FOR (f:Function) REQUIRE (f.name, f.path, f.line_number) IS NODE KEY",
    "CREATE CONSTRAINT class_unique IF NOT EXISTS FOR (c:Class) REQUIRE (c.name, c.path, c.line_number) IS NODE KEY",
    "CREATE CONSTRAINT trait_unique IF NOT EXISTS FOR (t:Trait) REQUIRE (t.name, t.path, t.line_number) IS NODE KEY",
    "CREATE CONSTRAINT interface_unique IF NOT EXISTS FOR (i:Interface) REQUIRE (i.name, i.path, i.line_number) IS NODE KEY",
    "CREATE CONSTRAINT macro_unique IF NOT EXISTS FOR (m:Macro) REQUIRE (m.name, m.path, m.line_number) IS NODE KEY",
    "CREATE CONSTRAINT variable_unique IF NOT EXISTS FOR (v:Variable) REQUIRE (v.name, v.path, v.line_number) IS NODE KEY",
    "CREATE CONSTRAINT module_name IF NOT EXISTS FOR (m:Module) REQUIRE m.name IS UNIQUE",
    "CREATE CONSTRAINT struct_cpp IF NOT EXISTS FOR (cstruct: Struct) REQUIRE (cstruct.name, cstruct.path, cstruct.line_number) IS NODE KEY",
    "CREATE CONSTRAINT enum_cpp IF NOT EXISTS FOR (cenum: Enum) REQUIRE (cenum.name, cenum.path, cenum.line_number) IS NODE KEY",
    "CREATE CONSTRAINT union_cpp IF NOT EXISTS FOR (cunion: Union) REQUIRE (cunion.name, cunion.path, cunion.line_number) IS NODE KEY",
    "CREATE CONSTRAINT annotation_unique IF NOT EXISTS FOR (a:Annotation) REQUIRE (a.name, a.path, a.line_number) IS NODE KEY",
    "CREATE CONSTRAINT record_unique IF NOT EXISTS FOR (r:Record) REQUIRE (r.name, r.path, r.line_number) IS NODE KEY",
    "CREATE CONSTRAINT property_unique IF NOT EXISTS FOR (p:Property) REQUIRE (p.name, p.path, p.line_number) IS NODE KEY",
    "CREATE CONSTRAINT k8s_resource_unique IF NOT EXISTS FOR (k:K8sResource) REQUIRE (k.name, k.kind, k.path, k.line_number) IS NODE KEY",
    "CREATE CONSTRAINT argocd_app_unique IF NOT EXISTS FOR (a:ArgoCDApplication) REQUIRE (a.name, a.path, a.line_number) IS NODE KEY",
    "CREATE CONSTRAINT argocd_appset_unique IF NOT EXISTS FOR (a:ArgoCDApplicationSet) REQUIRE (a.name, a.path, a.line_number) IS NODE KEY",
    "CREATE CONSTRAINT xrd_unique IF NOT EXISTS FOR (x:CrossplaneXRD) REQUIRE (x.name, x.path, x.line_number) IS NODE KEY",
    "CREATE CONSTRAINT composition_unique IF NOT EXISTS FOR (c:CrossplaneComposition) REQUIRE (c.name, c.path, c.line_number) IS NODE KEY",
    "CREATE CONSTRAINT claim_unique IF NOT EXISTS FOR (cl:CrossplaneClaim) REQUIRE (cl.name, cl.kind, cl.path, cl.line_number) IS NODE KEY",
    "CREATE CONSTRAINT kustomize_unique IF NOT EXISTS FOR (ko:KustomizeOverlay) REQUIRE ko.path IS UNIQUE",
    "CREATE CONSTRAINT helm_chart_unique IF NOT EXISTS FOR (h:HelmChart) REQUIRE (h.name, h.path) IS NODE KEY",
    "CREATE CONSTRAINT helm_values_unique IF NOT EXISTS FOR (hv:HelmValues) REQUIRE hv.path IS UNIQUE",
    "CREATE CONSTRAINT tf_resource_unique IF NOT EXISTS FOR (r:TerraformResource) REQUIRE (r.name, r.path, r.line_number) IS NODE KEY",
    "CREATE CONSTRAINT tf_variable_unique IF NOT EXISTS FOR (v:TerraformVariable) REQUIRE (v.name, v.path, v.line_number) IS NODE KEY",
    "CREATE CONSTRAINT tf_output_unique IF NOT EXISTS FOR (o:TerraformOutput) REQUIRE (o.name, o.path, o.line_number) IS NODE KEY",
    "CREATE CONSTRAINT tf_module_unique IF NOT EXISTS FOR (m:TerraformModule) REQUIRE (m.name, m.path) IS NODE KEY",
    "CREATE CONSTRAINT tf_datasource_unique IF NOT EXISTS FOR (ds:TerraformDataSource) REQUIRE (ds.name, ds.path, ds.line_number) IS NODE KEY",
    "CREATE CONSTRAINT tf_provider_unique IF NOT EXISTS FOR (p:TerraformProvider) REQUIRE (p.name, p.path, p.line_number) IS NODE KEY",
    "CREATE CONSTRAINT tf_local_unique IF NOT EXISTS FOR (l:TerraformLocal) REQUIRE (l.name, l.path, l.line_number) IS NODE KEY",
    "CREATE CONSTRAINT tg_config_unique IF NOT EXISTS FOR (tg:TerragruntConfig) REQUIRE tg.path IS UNIQUE",
    "CREATE CONSTRAINT cf_resource_unique IF NOT EXISTS FOR (r:CloudFormationResource) REQUIRE (r.name, r.path, r.line_number) IS NODE KEY",
    "CREATE CONSTRAINT cf_parameter_unique IF NOT EXISTS FOR (p:CloudFormationParameter) REQUIRE (p.name, p.path, p.line_number) IS NODE KEY",
    "CREATE CONSTRAINT cf_output_unique IF NOT EXISTS FOR (o:CloudFormationOutput) REQUIRE (o.name, o.path, o.line_number) IS NODE KEY",
    "CREATE CONSTRAINT ecosystem_name IF NOT EXISTS FOR (e:Ecosystem) REQUIRE e.name IS UNIQUE",
    "CREATE CONSTRAINT tier_name IF NOT EXISTS FOR (t:Tier) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT workload_id IF NOT EXISTS FOR (w:Workload) REQUIRE w.id IS UNIQUE",
    "CREATE CONSTRAINT workload_instance_id IF NOT EXISTS FOR (i:WorkloadInstance) REQUIRE i.id IS UNIQUE",
    "CREATE INDEX function_lang IF NOT EXISTS FOR (f:Function) ON (f.lang)",
    "CREATE INDEX class_lang IF NOT EXISTS FOR (c:Class) ON (c.lang)",
    "CREATE INDEX annotation_lang IF NOT EXISTS FOR (a:Annotation) ON (a.lang)",
    "CREATE INDEX k8s_kind IF NOT EXISTS FOR (k:K8sResource) ON (k.kind)",
    "CREATE INDEX k8s_namespace IF NOT EXISTS FOR (k:K8sResource) ON (k.namespace)",
    "CREATE INDEX tf_resource_type IF NOT EXISTS FOR (r:TerraformResource) ON (r.resource_type)",
    "CREATE INDEX workload_name IF NOT EXISTS FOR (w:Workload) ON (w.name)",
    "CREATE INDEX workload_repo_id IF NOT EXISTS FOR (w:Workload) ON (w.repo_id)",
    "CREATE INDEX workload_instance_environment IF NOT EXISTS FOR (i:WorkloadInstance) ON (i.environment)",
    "CREATE INDEX function_name IF NOT EXISTS FOR (f:Function) ON (f.name)",
    "CREATE INDEX class_name IF NOT EXISTS FOR (c:Class) ON (c.name)",
    "CREATE CONSTRAINT parameter_unique IF NOT EXISTS FOR (p:Parameter) REQUIRE (p.name, p.path, p.function_line_number) IS NODE KEY",
]
_SCHEMA_STATEMENTS.extend(_UID_CONSTRAINT_STATEMENTS)

_NEO4J_FULLTEXT_STATEMENTS = [
    "CALL db.index.fulltext.createNodeIndex('code_search_index', ['Function', 'Class', 'Variable'], ['name', 'source', 'docstring'])",
    "CALL db.index.fulltext.createNodeIndex('infra_search_index', ['K8sResource', 'TerraformResource', 'ArgoCDApplication', 'ArgoCDApplicationSet', 'CrossplaneXRD', 'CrossplaneComposition', 'CrossplaneClaim', 'KustomizeOverlay', 'HelmChart', 'HelmValues', 'TerraformVariable', 'TerraformOutput', 'TerraformModule', 'TerraformDataSource', 'TerraformProvider', 'TerraformLocal', 'TerragruntConfig', 'CloudFormationResource', 'CloudFormationParameter', 'CloudFormationOutput'], ['name', 'kind', 'resource_type'])",
]

_FALKORDB_FULLTEXT_STATEMENTS = [
    "CALL db.idx.fulltext.createNodeIndex('Function', 'name', 'source', 'docstring')",
    "CALL db.idx.fulltext.createNodeIndex('Class', 'name', 'source', 'docstring')",
]


def _schema_statements_for_capabilities(
    capabilities: GraphStoreCapabilities,
) -> tuple[str, ...]:
    """Return schema statements implied by one graph-store capability contract."""

    statements = list(_SCHEMA_STATEMENTS)
    if capabilities.fulltext_index_strategy == "neo4j_fulltext":
        statements.extend(_NEO4J_FULLTEXT_STATEMENTS)
    elif capabilities.fulltext_index_strategy == "falkordb_procedure":
        statements.extend(_FALKORDB_FULLTEXT_STATEMENTS)
    return tuple(statements)


def create_schema(builder: Any, *, info_logger_fn: Any, warning_logger_fn: Any) -> None:
    """Create constraints and indexes for the code graph.

    Args:
        builder: ``GraphBuilder`` facade instance.
        info_logger_fn: Informational logger callable.
        warning_logger_fn: Warning logger callable.
    """
    capabilities_getter = getattr(builder.db_manager, "graph_store_capabilities", None)
    capabilities = (
        capabilities_getter()
        if callable(capabilities_getter)
        else graph_store_capabilities_for_backend(
            getattr(builder.db_manager, "get_backend_type", lambda: "neo4j")()
        )
    )

    with builder.driver.session() as session:
        try:
            for statement in _schema_statements_for_capabilities(capabilities):
                session.run(statement)

            info_logger_fn("Database schema verified/created successfully")
        except Exception as exc:
            warning_logger_fn(f"Schema creation warning: {exc}")


__all__ = ["create_schema", "_schema_statements_for_capabilities"]
