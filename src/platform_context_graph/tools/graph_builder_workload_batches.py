"""Compatibility facade for workload finalization batch helpers."""

from ..resolution.workloads.batches import delete_orphan_platform_rows
from ..resolution.workloads.batches import retract_infrastructure_platform_rows
from ..resolution.workloads.batches import retract_instance_rows
from ..resolution.workloads.batches import retract_repo_dependency_rows
from ..resolution.workloads.batches import retract_stale_workload_rows
from ..resolution.workloads.batches import retract_workload_dependency_rows
from ..resolution.workloads.batches import write_deployment_source_rows
from ..resolution.workloads.batches import write_infrastructure_platform_rows
from ..resolution.workloads.batches import write_instance_rows
from ..resolution.workloads.batches import write_repo_dependency_rows
from ..resolution.workloads.batches import write_runtime_platform_rows
from ..resolution.workloads.batches import write_workload_dependency_rows
from ..resolution.workloads.batches import write_workload_rows

__all__ = [
    "delete_orphan_platform_rows",
    "retract_infrastructure_platform_rows",
    "retract_instance_rows",
    "retract_repo_dependency_rows",
    "retract_stale_workload_rows",
    "retract_workload_dependency_rows",
    "write_deployment_source_rows",
    "write_infrastructure_platform_rows",
    "write_instance_rows",
    "write_repo_dependency_rows",
    "write_runtime_platform_rows",
    "write_workload_dependency_rows",
    "write_workload_rows",
]
