"""MCP handler functions for repository, bundle, and job operations."""

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ....core.bundle_registry import BundleRegistry
from ....core.jobs import JobManager, JobStatus
from ....core.pcg_bundle import PCGBundle
from ....query import repositories as repository_queries
from ....tools.code_finder import CodeFinder
from ....tools.graph_builder import GraphBuilder
from ....utils.debug_log import debug_log


def list_indexed_repositories(code_finder: CodeFinder, **args: Any) -> dict[str, Any]:
    """Tool to list indexed repositories."""
    try:
        debug_log("Listing indexed repositories.")
        results = code_finder.list_indexed_repositories()
        return {"success": True, "repositories": results}
    except Exception as exc:
        debug_log(f"Error listing indexed repositories: {str(exc)}")
        return {"error": f"Failed to list indexed repositories: {str(exc)}"}


def delete_repository(graph_builder: GraphBuilder, **args: Any) -> dict[str, Any]:
    """Tool to delete a repository from the graph."""
    repo_path = args.get("repo_path")
    if not isinstance(repo_path, str) or not repo_path.strip():
        return {"error": "The 'repo_path' argument is required."}
    try:
        debug_log(f"Deleting repository: {repo_path}")
        if graph_builder.delete_repository_from_graph(repo_path):
            return {
                "success": True,
                "message": f"Repository '{repo_path}' deleted successfully.",
            }
        else:
            return {
                "success": False,
                "message": f"Repository '{repo_path}' not found in the graph.",
            }
    except Exception as exc:
        debug_log(f"Error deleting repository: {str(exc)}")
        return {"error": f"Failed to delete repository: {str(exc)}"}


def check_job_status(job_manager: JobManager, **args: Any) -> dict[str, Any]:
    """Tool to check job status."""
    job_id = args.get("job_id")
    if not job_id:
        return {"error": "Job ID is a required argument."}

    try:
        job = job_manager.get_job(job_id)

        if not job:
            return {
                "success": True,  # Return success to avoid generic error wrapper
                "status": "not_found",
                "message": f"Job with ID '{job_id}' not found. The ID may be incorrect or the job may have been cleared after a server restart.",
            }

        job_dict = asdict(job)

        if job.status == JobStatus.RUNNING:
            if job.estimated_time_remaining:
                remaining = job.estimated_time_remaining
                job_dict["estimated_time_remaining_human"] = (
                    f"{int(remaining // 60)}m {int(remaining % 60)}s"
                    if remaining >= 60
                    else f"{int(remaining)}s"
                )

            if job.start_time:
                elapsed = (datetime.now() - job.start_time).total_seconds()
                job_dict["elapsed_time_human"] = (
                    f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
                    if elapsed >= 60
                    else f"{int(elapsed)}s"
                )

        elif job.status == JobStatus.COMPLETED and job.start_time and job.end_time:
            duration = (job.end_time - job.start_time).total_seconds()
            job_dict["actual_duration_human"] = (
                f"{int(duration // 60)}m {int(duration % 60)}s"
                if duration >= 60
                else f"{int(duration)}s"
            )

        job_dict["start_time"] = job.start_time.strftime("%Y-%m-%d %H:%M:%S")
        if job.end_time:
            job_dict["end_time"] = job.end_time.strftime("%Y-%m-%d %H:%M:%S")

        job_dict["status"] = job.status.value

        return {"success": True, "job": job_dict}

    except Exception as exc:
        debug_log(f"Error checking job status: {str(exc)}")
        return {"error": f"Failed to check job status: {str(exc)}"}


def list_jobs(job_manager: JobManager) -> dict[str, Any]:
    """Tool to list all jobs."""
    try:
        jobs = job_manager.list_jobs()

        jobs_data = []
        for job in jobs:
            job_dict = asdict(job)
            job_dict["status"] = job.status.value
            job_dict["start_time"] = job.start_time.strftime("%Y-%m-%d %H:%M:%S")
            if job.end_time:
                job_dict["end_time"] = job.end_time.strftime("%Y-%m-%d %H:%M:%S")
            jobs_data.append(job_dict)

        jobs_data.sort(key=lambda x: x["start_time"], reverse=True)

        return {"success": True, "jobs": jobs_data, "total_jobs": len(jobs_data)}

    except Exception as exc:
        debug_log(f"Error listing jobs: {str(exc)}")
        return {"error": f"Failed to list jobs: {str(exc)}"}


def load_bundle(code_finder: CodeFinder, **args: Any) -> dict[str, Any]:
    """Tool to load a .pcg bundle into the database."""

    bundle_name = args.get("bundle_name")
    clear_existing = args.get("clear_existing", False)

    if not bundle_name:
        return {"error": "bundle_name is required"}

    try:
        debug_log(f"Loading bundle: {bundle_name}")

        # Check if bundle exists locally
        bundle_path = Path(bundle_name)

        # If it doesn't exist as-is, try with .pcg extension
        if not bundle_path.exists() and not str(bundle_name).endswith(".pcg"):
            bundle_path = Path(f"{bundle_name}.pcg")

        if not bundle_path.exists():
            # Try to download from registry
            debug_log(f"Bundle {bundle_name} not found locally, checking registry...")
            download_url, bundle_meta, error = BundleRegistry.find_bundle_download_info(
                bundle_name
            )

            if not download_url:
                return {
                    "error": f"Bundle not found locally or in registry: {bundle_name}. {error}"
                }

            # Determine output filename from metadata
            bundle_metadata = bundle_meta or {}
            filename = bundle_metadata.get("bundle_name", f"{bundle_name}.pcg")
            # Save to current working directory
            target_path = Path.cwd() / filename

            debug_log(f"Downloading bundle to {target_path}...")
            try:
                BundleRegistry.download_file(download_url, target_path)
                bundle_path = target_path
                debug_log(f"Successfully downloaded to {bundle_path}")
            except Exception as exc:
                return {"error": f"Failed to download bundle: {str(exc)}"}

            # Verify the downloaded file exists
            if not bundle_path.exists():
                return {
                    "error": f"Download completed but file not found at {bundle_path}"
                }

        # Load the bundle using PCGBundle core class
        bundle = PCGBundle(code_finder.db_manager)
        success, message = bundle.import_from_bundle(
            bundle_path=bundle_path, clear_existing=clear_existing
        )

        if success:
            stats = {}
            # Parse simple stats from message if possible, or just return success
            if "Nodes:" in message:
                # Best effort parsing, not critical
                pass

            return {"success": True, "message": message, "stats": stats}
        else:
            return {"error": message}

    except Exception as exc:
        debug_log(f"Error loading bundle: {str(exc)}")
        return {"error": f"Failed to load bundle: {str(exc)}"}


def search_registry_bundles(code_finder: CodeFinder, **args: Any) -> dict[str, Any]:
    """Tool to search for bundles in the registry."""
    query = args.get("query", "").lower()
    unique_only = args.get("unique_only", False)

    try:
        debug_log(f"Searching registry for: {query}")

        # Fetch directly from core registry
        bundles = BundleRegistry.fetch_available_bundles()

        if not bundles:
            return {
                "success": True,
                "bundles": [],
                "total": 0,
                "message": "No bundles found in registry",
            }

        # Filter by query if provided
        if query:
            filtered_bundles = []
            for bundle in bundles:
                name = bundle.get("name", "").lower()
                repo = bundle.get("repo", "").lower()
                full_name = bundle.get("full_name", "").lower()

                if query in name or query in repo or query in full_name:
                    filtered_bundles.append(bundle)
            bundles = filtered_bundles

        # If unique_only, keep only most recent version per package
        if unique_only:
            unique_bundles = {}
            for bundle in bundles:
                base_name = bundle.get("name", "unknown")
                if base_name not in unique_bundles:
                    unique_bundles[base_name] = bundle
                else:
                    current_time = bundle.get("generated_at", "")
                    existing_time = unique_bundles[base_name].get("generated_at", "")
                    if current_time > existing_time:
                        unique_bundles[base_name] = bundle
            bundles = list(unique_bundles.values())

        # Sort by name
        bundles.sort(key=lambda b: (b.get("name", ""), b.get("full_name", "")))

        return {
            "success": True,
            "bundles": bundles,
            "total": len(bundles),
            "query": query if query else "all",
            "unique_only": unique_only,
        }

    except Exception as exc:
        debug_log(f"Error searching registry: {str(exc)}")
        return {"error": f"Failed to search registry: {str(exc)}"}


def get_repository_stats(code_finder: CodeFinder, **args: Any) -> dict[str, Any]:
    """Tool to get statistics about indexed repositories."""
    repo_path = args.get("repo_path")

    try:
        debug_log(f"Getting stats for: {repo_path or 'all repositories'}")
        return repository_queries.get_repository_stats(
            code_finder,
            repo_id=repo_path,
        )

    except Exception as exc:
        debug_log(f"Error getting stats: {str(exc)}")
        return {"error": f"Failed to get stats: {str(exc)}"}
