"""Schema constants and initialization helpers for the Kuzu backend."""

from __future__ import annotations

from typing import Sequence

from platform_context_graph.utils.debug_log import debug_log, warning_logger

KUZU_NODE_TABLES: Sequence[tuple[str, str]] = [
    (
        "Repository",
        "path STRING, name STRING, is_dependency BOOLEAN, PRIMARY KEY (path)",
    ),
    (
        "File",
        "path STRING, name STRING, relative_path STRING, is_dependency BOOLEAN, PRIMARY KEY (path)",
    ),
    ("Directory", "path STRING, name STRING, PRIMARY KEY (path)"),
    (
        "Module",
        "name STRING, lang STRING, full_import_name STRING, PRIMARY KEY (name)",
    ),
    (
        "Function",
        "uid STRING, name STRING, path STRING, line_number INT64, end_line INT64, source STRING, docstring STRING, lang STRING, cyclomatic_complexity INT64, context STRING, context_type STRING, class_context STRING, is_dependency BOOLEAN, decorators STRING[], args STRING[], PRIMARY KEY (uid)",
    ),
    (
        "Class",
        "uid STRING, name STRING, path STRING, line_number INT64, end_line INT64, source STRING, docstring STRING, lang STRING, is_dependency BOOLEAN, decorators STRING[], PRIMARY KEY (uid)",
    ),
    (
        "Variable",
        "uid STRING, name STRING, path STRING, line_number INT64, source STRING, docstring STRING, lang STRING, value STRING, context STRING, is_dependency BOOLEAN, PRIMARY KEY (uid)",
    ),
    (
        "Trait",
        "uid STRING, name STRING, path STRING, line_number INT64, end_line INT64, source STRING, docstring STRING, lang STRING, is_dependency BOOLEAN, PRIMARY KEY (uid)",
    ),
    (
        "Interface",
        "uid STRING, name STRING, path STRING, line_number INT64, end_line INT64, source STRING, docstring STRING, lang STRING, is_dependency BOOLEAN, PRIMARY KEY (uid)",
    ),
    (
        "Macro",
        "uid STRING, name STRING, path STRING, line_number INT64, end_line INT64, source STRING, docstring STRING, lang STRING, is_dependency BOOLEAN, PRIMARY KEY (uid)",
    ),
    (
        "Struct",
        "uid STRING, name STRING, path STRING, line_number INT64, end_line INT64, source STRING, docstring STRING, lang STRING, is_dependency BOOLEAN, PRIMARY KEY (uid)",
    ),
    (
        "Enum",
        "uid STRING, name STRING, path STRING, line_number INT64, end_line INT64, source STRING, docstring STRING, lang STRING, is_dependency BOOLEAN, PRIMARY KEY (uid)",
    ),
    (
        "Union",
        "uid STRING, name STRING, path STRING, line_number INT64, end_line INT64, source STRING, docstring STRING, lang STRING, is_dependency BOOLEAN, PRIMARY KEY (uid)",
    ),
    (
        "Annotation",
        "uid STRING, name STRING, path STRING, line_number INT64, end_line INT64, source STRING, docstring STRING, lang STRING, is_dependency BOOLEAN, PRIMARY KEY (uid)",
    ),
    (
        "Record",
        "uid STRING, name STRING, path STRING, line_number INT64, end_line INT64, source STRING, docstring STRING, lang STRING, is_dependency BOOLEAN, PRIMARY KEY (uid)",
    ),
    (
        "Property",
        "uid STRING, name STRING, path STRING, line_number INT64, end_line INT64, source STRING, docstring STRING, lang STRING, is_dependency BOOLEAN, PRIMARY KEY (uid)",
    ),
    (
        "Parameter",
        "uid STRING, name STRING, path STRING, function_line_number INT64, PRIMARY KEY (uid)",
    ),
    (
        "K8sResource",
        "uid STRING, name STRING, kind STRING, api_version STRING, namespace STRING, labels STRING, annotations STRING, container_images STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "ArgoCDApplication",
        "uid STRING, name STRING, namespace STRING, project STRING, source_repo STRING, source_path STRING, source_revision STRING, dest_server STRING, dest_namespace STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "ArgoCDApplicationSet",
        "uid STRING, name STRING, namespace STRING, generators STRING, project STRING, dest_namespace STRING, source_repos STRING, source_paths STRING, source_roots STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "CrossplaneXRD",
        "uid STRING, name STRING, group STRING, kind STRING, plural STRING, claim_kind STRING, claim_plural STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "CrossplaneComposition",
        "uid STRING, name STRING, composite_api_version STRING, composite_kind STRING, resource_count INT64, resource_names STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "CrossplaneClaim",
        "uid STRING, name STRING, kind STRING, api_version STRING, namespace STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "KustomizeOverlay",
        "path STRING, name STRING, namespace STRING, resources STRING[], patches STRING[], line_number INT64, lang STRING, PRIMARY KEY (path)",
    ),
    (
        "HelmChart",
        "uid STRING, name STRING, version STRING, app_version STRING, chart_type STRING, description STRING, dependencies STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "HelmValues",
        "path STRING, name STRING, top_level_keys STRING, line_number INT64, lang STRING, PRIMARY KEY (path)",
    ),
    (
        "TerraformResource",
        "uid STRING, name STRING, resource_type STRING, resource_name STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "TerraformVariable",
        "uid STRING, name STRING, var_type STRING, default STRING, description STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "TerraformOutput",
        "uid STRING, name STRING, description STRING, value STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "TerraformModule",
        "uid STRING, name STRING, source STRING, version STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "TerraformDataSource",
        "uid STRING, name STRING, data_type STRING, data_name STRING, path STRING, line_number INT64, lang STRING, PRIMARY KEY (uid)",
    ),
    (
        "TerragruntConfig",
        "path STRING, name STRING, terraform_source STRING, includes STRING, line_number INT64, lang STRING, PRIMARY KEY (path)",
    ),
    ("Ecosystem", "name STRING, org STRING, PRIMARY KEY (name)"),
    ("Tier", "name STRING, risk_level STRING, PRIMARY KEY (name)"),
]

KUZU_REL_TABLES: Sequence[tuple[str, str]] = [
    (
        "CONTAINS",
        "FROM File TO Function, FROM File TO Class, FROM File TO Variable, FROM File TO Trait, FROM File TO Interface, FROM `Macro` TO `Macro`, FROM File TO `Macro`, FROM File TO Struct, FROM File TO Enum, FROM File TO `Union`, FROM File TO Annotation, FROM File TO Record, FROM File TO Property, FROM Repository TO Directory, FROM Directory TO Directory, FROM Directory TO File, FROM Repository TO File, FROM Class TO Function, FROM Function TO Function, FROM File TO K8sResource, FROM File TO ArgoCDApplication, FROM File TO ArgoCDApplicationSet, FROM File TO CrossplaneXRD, FROM File TO CrossplaneComposition, FROM File TO CrossplaneClaim, FROM File TO KustomizeOverlay, FROM File TO HelmChart, FROM File TO HelmValues, FROM File TO TerraformResource, FROM File TO TerraformVariable, FROM File TO TerraformOutput, FROM File TO TerraformModule, FROM File TO TerraformDataSource, FROM File TO TerragruntConfig, FROM Ecosystem TO Tier, FROM Tier TO Repository",
    ),
    (
        "CALLS",
        "FROM Function TO Function, FROM Function TO Class, FROM File TO Function, FROM File TO Class, FROM Class TO Function, FROM Class TO Class, line_number INT64, args STRING[], full_call_name STRING",
    ),
    (
        "IMPORTS",
        "FROM File TO Module, alias STRING, full_import_name STRING, imported_name STRING, line_number INT64",
    ),
    (
        "INHERITS",
        "FROM Class TO Class, FROM Record TO Record, FROM Interface TO Interface",
    ),
    ("HAS_PARAMETER", "FROM Function TO Parameter"),
    ("INCLUDES", "FROM Class TO Module"),
    (
        "IMPLEMENTS",
        "FROM Class TO Interface, FROM Struct TO Interface, FROM Record TO Interface",
    ),
    ("DEPENDS_ON", "FROM Repository TO Repository"),
    ("SOURCES_FROM", "FROM ArgoCDApplication TO Repository, FROM ArgoCDApplicationSet TO Repository"),
    ("SATISFIED_BY", "FROM CrossplaneClaim TO CrossplaneXRD"),
    ("IMPLEMENTED_BY", "FROM CrossplaneXRD TO CrossplaneComposition"),
    ("USES_MODULE", "FROM TerraformModule TO Repository"),
    ("DEPLOYS", "FROM ArgoCDApplication TO K8sResource, FROM ArgoCDApplicationSet TO K8sResource"),
    ("CONFIGURES", "FROM HelmValues TO HelmChart"),
    ("SELECTS", "FROM K8sResource TO K8sResource"),
    ("USES_IAM", "FROM K8sResource TO TerraformResource"),
    ("ROUTES_TO", "FROM K8sResource TO K8sResource"),
    ("PATCHES", "FROM KustomizeOverlay TO K8sResource"),
    ("RUNS_IMAGE", "FROM K8sResource TO Repository"),
]

KUZU_UID_MAP: dict[str, list[str]] = {
    "Function": ["name", "path", "line_number"],
    "Class": ["name", "path", "line_number"],
    "Variable": ["name", "path", "line_number"],
    "Trait": ["name", "path", "line_number"],
    "Interface": ["name", "path", "line_number"],
    "Macro": ["name", "path", "line_number"],
    "Struct": ["name", "path", "line_number"],
    "Enum": ["name", "path", "line_number"],
    "Union": ["name", "path", "line_number"],
    "Annotation": ["name", "path", "line_number"],
    "Record": ["name", "path", "line_number"],
    "Property": ["name", "path", "line_number"],
    "Parameter": ["name", "path", "function_line_number"],
}

KUZU_SCHEMA_MAP: dict[str, set[str]] = {
    "Repository": {"path", "name", "is_dependency"},
    "File": {"path", "name", "relative_path", "is_dependency"},
    "Directory": {"path", "name"},
    "Module": {"name", "lang", "full_import_name"},
    "Function": {
        "uid",
        "name",
        "path",
        "line_number",
        "end_line",
        "source",
        "docstring",
        "lang",
        "cyclomatic_complexity",
        "context",
        "context_type",
        "class_context",
        "is_dependency",
        "decorators",
        "args",
    },
    "Class": {
        "uid",
        "name",
        "path",
        "line_number",
        "end_line",
        "source",
        "docstring",
        "lang",
        "is_dependency",
        "decorators",
    },
    "Variable": {
        "uid",
        "name",
        "path",
        "line_number",
        "source",
        "docstring",
        "lang",
        "value",
        "context",
        "is_dependency",
    },
    "Trait": {
        "uid",
        "name",
        "path",
        "line_number",
        "end_line",
        "source",
        "docstring",
        "lang",
        "is_dependency",
    },
    "Interface": {
        "uid",
        "name",
        "path",
        "line_number",
        "end_line",
        "source",
        "docstring",
        "lang",
        "is_dependency",
    },
    "Macro": {
        "uid",
        "name",
        "path",
        "line_number",
        "end_line",
        "source",
        "docstring",
        "lang",
        "is_dependency",
    },
    "Struct": {
        "uid",
        "name",
        "path",
        "line_number",
        "end_line",
        "source",
        "docstring",
        "lang",
        "is_dependency",
    },
    "Enum": {
        "uid",
        "name",
        "path",
        "line_number",
        "end_line",
        "source",
        "docstring",
        "lang",
        "is_dependency",
    },
    "Union": {
        "uid",
        "name",
        "path",
        "line_number",
        "end_line",
        "source",
        "docstring",
        "lang",
        "is_dependency",
    },
    "Annotation": {
        "uid",
        "name",
        "path",
        "line_number",
        "end_line",
        "source",
        "docstring",
        "lang",
        "is_dependency",
    },
    "Record": {
        "uid",
        "name",
        "path",
        "line_number",
        "end_line",
        "source",
        "docstring",
        "lang",
        "is_dependency",
    },
    "Property": {
        "uid",
        "name",
        "path",
        "line_number",
        "end_line",
        "source",
        "docstring",
        "lang",
        "is_dependency",
    },
    "Parameter": {"uid", "name", "path", "function_line_number"},
}

KUZU_LABELS_TO_ESCAPE = ["Macro", "Union", "Property", "CONTAINS", "CALLS"]


def initialize_kuzu_schema(conn) -> None:
    """Create the Kuzu schema if the expected tables do not already exist.

    Args:
        conn: Active Kuzu connection used to issue schema statements.
    """
    for table_name, schema in KUZU_NODE_TABLES:
        try:
            conn.execute(f"CREATE NODE TABLE `{table_name}`({schema})")
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                warning_logger(f"Kuzu Schema Node Error ({table_name}): {exc}")
                debug_log(f"Kuzu Schema Node Error ({table_name}): {exc}")

    for table_name, schema in KUZU_REL_TABLES:
        try:
            conn.execute(f"CREATE REL TABLE `{table_name}`({schema})")
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                warning_logger(f"Kuzu Schema Rel Error ({table_name}): {exc}")
                debug_log(f"Kuzu Schema Rel Error ({table_name}): {exc}")
