"""Remote facts-admin command helpers for the CLI."""

from __future__ import annotations

from typing import Any

import typer

from .remote import RemoteAPIError
from .remote import print_json_payload
from .remote import request_json
from .remote import resolve_remote_target


def run_remote_admin_facts_replay(
    main_module: Any,
    *,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
    work_item_ids: list[str] | None,
    repository_id: str | None,
    source_run_id: str | None,
    work_type: str | None,
    failure_class: str | None,
    operator_note: str | None,
    limit: int,
) -> None:
    """Replay failed facts-first work items through the admin API."""

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
            path="/api/v0/admin/facts/replay",
            json_body={
                "work_item_ids": work_item_ids or None,
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "work_type": work_type,
                "failure_class": failure_class,
                "operator_note": operator_note,
                "limit": limit,
            },
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote facts replay failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc

    main_module.console.print(
        f"[bold cyan]Facts Replay:[/bold cyan] {payload.get('status', 'unknown')}"
    )
    main_module.console.print(
        f"[cyan]Replayed:[/cyan] {payload.get('replayed_count', 0)}"
    )
    work_item_ids = payload.get("work_item_ids") or []
    if work_item_ids:
        main_module.console.print(
            "[cyan]Work items:[/cyan] " + ", ".join(str(item) for item in work_item_ids)
        )


def run_remote_admin_facts_list_work_items(
    main_module: Any,
    *,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
    statuses: list[str] | None,
    repository_id: str | None,
    source_run_id: str | None,
    work_type: str | None,
    failure_class: str | None,
    limit: int,
) -> None:
    """List fact work items through the admin API."""

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
            path="/api/v0/admin/facts/work-items/query",
            json_body={
                "statuses": statuses or None,
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "work_type": work_type,
                "failure_class": failure_class,
                "limit": limit,
            },
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote fact work-item query failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc

    print_json_payload(main_module.console, payload)


def run_remote_admin_facts_list_decisions(
    main_module: Any,
    *,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
    repository_id: str,
    source_run_id: str,
    decision_type: str | None,
    include_evidence: bool,
    limit: int,
) -> None:
    """List projection decisions through the admin API."""

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
            path="/api/v0/admin/facts/decisions/query",
            json_body={
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "decision_type": decision_type,
                "include_evidence": include_evidence,
                "limit": limit,
            },
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote projection decision query failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc

    print_json_payload(main_module.console, payload)


def run_remote_admin_facts_dead_letter(
    main_module: Any,
    *,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
    work_item_ids: list[str] | None,
    repository_id: str | None,
    source_run_id: str | None,
    work_type: str | None,
    failure_class: str,
    operator_note: str | None,
    limit: int,
) -> None:
    """Dead-letter selected fact work items through the admin API."""

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
            path="/api/v0/admin/facts/dead-letter",
            json_body={
                "work_item_ids": work_item_ids or None,
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "work_type": work_type,
                "failure_class": failure_class,
                "operator_note": operator_note,
                "limit": limit,
            },
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote fact dead-letter failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc

    print_json_payload(main_module.console, payload)


def run_remote_admin_facts_skip(
    main_module: Any,
    *,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
    repository_id: str,
    operator_note: str | None,
) -> None:
    """Skip one repository's actionable fact work items through the admin API."""

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
            path="/api/v0/admin/facts/skip",
            json_body={
                "repository_id": repository_id,
                "operator_note": operator_note,
            },
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote fact skip failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc

    print_json_payload(main_module.console, payload)


def run_remote_admin_fact_backfill(
    main_module: Any,
    *,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
    repository_id: str | None,
    source_run_id: str | None,
    operator_note: str | None,
) -> None:
    """Create one durable fact backfill request through the admin API."""

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
            path="/api/v0/admin/facts/backfill",
            json_body={
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "operator_note": operator_note,
            },
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote fact backfill request failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc

    main_module.console.print(
        f"[bold cyan]Fact Backfill:[/bold cyan] {payload.get('status', 'unknown')}"
    )
    request_payload = payload.get("backfill_request") or {}
    if request_payload.get("backfill_request_id"):
        main_module.console.print(
            "[cyan]Backfill request:[/cyan] "
            f"{request_payload['backfill_request_id']}"
        )


def run_remote_admin_fact_replay_events(
    main_module: Any,
    *,
    service_url: str | None,
    api_key: str | None,
    profile: str | None,
    repository_id: str | None,
    source_run_id: str | None,
    work_item_id: str | None,
    failure_class: str | None,
    limit: int,
) -> None:
    """List fact replay-event audit rows through the admin API."""

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
            path="/api/v0/admin/facts/replay-events/query",
            json_body={
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "work_item_id": work_item_id,
                "failure_class": failure_class,
                "limit": limit,
            },
        )
    except RemoteAPIError as exc:
        main_module.console.print(
            f"[bold red]Remote replay-event query failed:[/bold red] {exc}"
        )
        raise typer.Exit(code=1) from exc

    print_json_payload(main_module.console, payload)
