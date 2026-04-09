"""Exports for durable shared projection intent storage and emission."""

from .dependency_domain import build_repo_dependency_intent_rows
from .dependency_domain import build_workload_dependency_intent_rows
from .dependency_domain import existing_repo_dependency_rows
from .dependency_domain import existing_workload_dependency_rows
from .dependency_domain import shared_dependency_projection_metrics
from .emission import emit_dependency_intents
from .emission import emit_platform_infra_intents
from .emission import emit_platform_runtime_intents
from .followup import run_inline_shared_followup
from .models import SharedProjectionIntentRow
from .models import build_shared_projection_intent
from .partitioning import partition_for_key
from .partitioning import rows_for_partition
from .postgres import PostgresSharedProjectionIntentStore
from .runtime import DEPENDENCY_PROJECTION_DOMAINS
from .runtime import PLATFORM_INFRA_PROJECTION_DOMAIN
from .runtime import dependency_shared_projection_worker_enabled
from .runtime import process_dependency_partition_once
from .runtime import process_platform_partition_once
from .runtime import platform_shared_projection_worker_enabled

__all__ = [
    "PostgresSharedProjectionIntentStore",
    "SharedProjectionIntentRow",
    "DEPENDENCY_PROJECTION_DOMAINS",
    "PLATFORM_INFRA_PROJECTION_DOMAIN",
    "build_repo_dependency_intent_rows",
    "build_shared_projection_intent",
    "build_workload_dependency_intent_rows",
    "dependency_shared_projection_worker_enabled",
    "emit_dependency_intents",
    "emit_platform_infra_intents",
    "emit_platform_runtime_intents",
    "existing_repo_dependency_rows",
    "existing_workload_dependency_rows",
    "partition_for_key",
    "process_dependency_partition_once",
    "platform_shared_projection_worker_enabled",
    "process_platform_partition_once",
    "rows_for_partition",
    "run_inline_shared_followup",
    "shared_dependency_projection_metrics",
]
