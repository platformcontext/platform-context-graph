"""Remote-aware command helpers shared across CLI command modules."""

from __future__ import annotations

from typing import Any

import typer

from ..query.shared_projection_tuning_format import format_tuning_report_table
from .remote import (
    RemoteAPIError,
    print_json_payload,
    remote_mode_requested,
    request_json,
    resolve_remote_target,
)


def render_remote_index_status(
    main_module: Any,
    *,
    target: str | None,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
) -> None:
    """Render remote checkpointed index status through the HTTP API."""

    remote_target = resolve_remote_target(
        service_url=service_url,
        api_key=api_key,
        profile=profile,
        require_remote=True,
    )
    try:
        summary = request_json(
            remote_target,
            method="GET",
            path="/api/v0/index-status",
            params={"target": target} if target else None,
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote index status failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc
    main_module.console.print(
        f"[bold cyan]Index Run:[/bold cyan] {summary['run_id']} "
        f"[dim]({summary['status']}, finalization={summary.get('finalization_status')})[/dim]"
    )
    main_module.console.print(f"[cyan]Root:[/cyan] {summary['root_path']}")
    main_module.console.print(
        "[cyan]Repositories:[/cyan] "
        f"{summary['completed_repositories']} completed / "
        f"{summary['failed_repositories']} failed / "
        f"{summary['pending_repositories']} pending "
        f"of {summary['repository_count']}"
    )


def render_remote_workspace_status(
    main_module: Any,
    *,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
) -> None:
    """Render remote ingester workspace status through the HTTP API."""

    remote_target = resolve_remote_target(
        service_url=service_url,
        api_key=api_key,
        profile=profile,
        require_remote=True,
    )
    try:
        status = request_json(
            remote_target,
            method="GET",
            path="/api/v0/ingesters/repository",
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote workspace status failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc
    main_module.console.print("[bold cyan]Workspace Status[/bold cyan]")
    main_module.console.print(
        f"[cyan]Ingester:[/cyan] {status.get('ingester', 'repository')}"
    )
    main_module.console.print(f"[cyan]Status:[/cyan] {status.get('status', 'unknown')}")
    if status.get("active_run_id"):
        main_module.console.print(f"[cyan]Active run:[/cyan] {status['active_run_id']}")
    main_module.console.print(
        f"[cyan]Repositories:[/cyan] total={status.get('repository_count', 0)} "
        f"completed={status.get('completed_repositories', 0)} "
        f"failed={status.get('failed_repositories', 0)} "
        f"pending={status.get('pending_repositories', 0)}"
    )
    shared_tuning = status.get("shared_projection_tuning")
    if isinstance(shared_tuning, dict):
        pending_repositories = int(
            status.get("shared_projection_pending_repositories", 0) or 0
        )
        pending_intents = int(shared_tuning.get("current_pending_intents", 0) or 0)
        oldest_age_seconds = float(
            shared_tuning.get("current_oldest_pending_age_seconds", 0.0) or 0.0
        )
        main_module.console.print(
            "[cyan]Shared follow-up:[/cyan] "
            f"repos={pending_repositories} "
            f"intents={pending_intents} "
            f"oldest={oldest_age_seconds:.1f}s"
        )
        recommendation = shared_tuning.get("recommended")
        if isinstance(recommendation, dict):
            recommended_setting = str(recommendation.get("setting") or "").strip()
            if recommended_setting:
                main_module.console.print(
                    f"[cyan]Recommended tuning:[/cyan] {recommended_setting}"
                )


def run_remote_admin_reindex(
    main_module: Any,
    *,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
    ingester: str,
    scope: str,
    force: bool,
) -> None:
    """Queue a remote ingester reindex request through the admin API."""

    remote_target = resolve_remote_target(
        service_url=service_url,
        api_key=api_key,
        profile=profile,
        require_remote=True,
    )
    try:
        payload = request_json(
            remote_target,
            method="POST",
            path="/api/v0/admin/reindex",
            json_body={
                "ingester": ingester,
                "scope": scope,
                "force": force,
            },
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote reindex request failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc

    main_module.console.print(
        f"[bold cyan]Remote Reindex:[/bold cyan] {payload.get('status', 'unknown')}"
    )
    main_module.console.print(
        f"[cyan]Request token:[/cyan] {payload.get('request_token')}"
    )
    main_module.console.print(
        f"[cyan]Scope:[/cyan] {payload.get('scope')} "
        f"[dim](force={payload.get('force')})[/dim]"
    )


def render_admin_tuning_report(
    main_module: Any,
    *,
    output_format: str,
    include_platform: bool,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
    local_report_builder: Any,
) -> None:
    """Render the deterministic shared-write tuning report locally or remotely."""

    if remote_mode_requested(service_url=service_url, profile=profile):
        remote_target = resolve_remote_target(
            service_url=service_url,
            api_key=api_key,
            profile=profile,
            require_remote=True,
        )
        try:
            payload = request_json(
                remote_target,
                method="GET",
                path="/api/v0/admin/shared-projection/tuning-report",
                params={"include_platform": "true"} if include_platform else None,
            )
        except RemoteAPIError as exc:
            main_module.console.print(
                f"[bold red]Remote tuning report failed:[/bold red] {exc}"
            )
            raise typer.Exit(code=1) from exc
    else:
        payload = local_report_builder(include_platform=include_platform)

    if output_format == "json":
        main_module.console.print_json(data=payload, default=str)
        return
    main_module.console.print(format_tuning_report_table(payload).rstrip("\n"))


def render_remote_search(
    main_module: Any,
    *,
    query: str,
    exact: bool,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
) -> None:
    """Render a remote code-search query result."""

    remote_target = resolve_remote_target(
        service_url=service_url,
        api_key=api_key,
        profile=profile,
        require_remote=True,
    )
    try:
        payload = request_json(
            remote_target,
            method="POST",
            path="/api/v0/code/search",
            json_body={
                "query": query,
                "exact": exact,
                "limit": 50,
            },
        )
    except RemoteAPIError as exc:
        main_module.console.print(f"[bold red]Remote find failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    print_json_payload(main_module.console, payload)


def render_remote_relationship_query(
    main_module: Any,
    *,
    query_type: str,
    target: str,
    context: str | None,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
    failure_label: str,
) -> None:
    """Render one remote code relationship query result."""

    remote_target = resolve_remote_target(
        service_url=service_url,
        api_key=api_key,
        profile=profile,
        require_remote=True,
    )
    try:
        payload = request_json(
            remote_target,
            method="POST",
            path="/api/v0/code/relationships",
            json_body={
                "query_type": query_type,
                "target": target,
                "context": context,
            },
        )
    except RemoteAPIError as exc:
        main_module.console.print(f"[bold red]{failure_label}:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    print_json_payload(main_module.console, payload)


def render_remote_complexity(
    main_module: Any,
    *,
    function_name: str | None,
    path: str | None,
    limit: int,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
) -> None:
    """Render a remote complexity query result."""

    remote_target = resolve_remote_target(
        service_url=service_url,
        api_key=api_key,
        profile=profile,
        require_remote=True,
    )
    try:
        payload = request_json(
            remote_target,
            method="POST",
            path="/api/v0/code/complexity",
            json_body={
                "mode": "function" if function_name else "top",
                "limit": limit,
                "function_name": function_name,
                "path": path,
            },
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote complexity analysis failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc
    print_json_payload(main_module.console, payload)


def render_remote_dead_code(
    main_module: Any,
    *,
    exclude_decorated_with: list[str] | None,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
) -> None:
    """Render a remote dead-code query result."""

    remote_target = resolve_remote_target(
        service_url=service_url,
        api_key=api_key,
        profile=profile,
        require_remote=True,
    )
    try:
        payload = request_json(
            remote_target,
            method="POST",
            path="/api/v0/code/dead-code",
            json_body={"exclude_decorated_with": exclude_decorated_with},
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote dead-code analysis failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc
    print_json_payload(main_module.console, payload)
