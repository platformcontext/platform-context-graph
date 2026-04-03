"""Admin runtime command registration for the CLI entrypoint."""

from __future__ import annotations

from typing import Any

import typer

from ..remote_commands import run_remote_admin_facts_replay
from ..remote_commands import run_remote_admin_reindex


def register_admin_commands(main_module: Any, admin_app: typer.Typer) -> None:
    """Register admin commands on the runtime CLI group."""

    admin_facts_app = typer.Typer(help="Facts-first queue administration commands")
    admin_app.add_typer(admin_facts_app, name="facts")

    @admin_app.command("reindex")
    def admin_reindex(
        service_url: str | None = typer.Option(
            None,
            "--service-url",
            help="Base URL of the remote PlatformContextGraph HTTP service.",
        ),
        api_key: str | None = typer.Option(
            None,
            "--api-key",
            help="Bearer token for the remote PlatformContextGraph HTTP service.",
        ),
        profile: str | None = typer.Option(
            None,
            "--profile",
            help="Named remote profile used to resolve service URL and token.",
        ),
        ingester: str = typer.Option(
            "repository",
            "--ingester",
            help="Ingester name to target for the remote reindex request.",
        ),
        scope: str = typer.Option(
            "workspace",
            "--scope",
            help="Reindex scope. Currently only 'workspace' is supported.",
        ),
        force: bool = typer.Option(
            True,
            "--force/--no-force",
            help=(
                "Whether the ingester should invalidate the existing checkpoint "
                "before rebuilding."
            ),
        ),
    ) -> None:
        """Queue a remote ingester reindex request through the admin API."""

        run_remote_admin_reindex(
            main_module,
            service_url=service_url,
            api_key=api_key,
            profile=profile,
            ingester=ingester,
            scope=scope,
            force=force,
        )

    @admin_facts_app.command("replay")
    def admin_facts_replay(
        service_url: str | None = typer.Option(
            None,
            "--service-url",
            help="Base URL of the remote PlatformContextGraph HTTP service.",
        ),
        api_key: str | None = typer.Option(
            None,
            "--api-key",
            help="Bearer token for the remote PlatformContextGraph HTTP service.",
        ),
        profile: str | None = typer.Option(
            None,
            "--profile",
            help="Named remote profile used to resolve service URL and token.",
        ),
        work_item_id: list[str] | None = typer.Option(
            None,
            "--work-item-id",
            help="Specific failed work item id(s) to replay.",
        ),
        repository_id: str | None = typer.Option(
            None,
            "--repository-id",
            help="Replay failed work items for one repository id.",
        ),
        source_run_id: str | None = typer.Option(
            None,
            "--source-run-id",
            help="Replay failed work items for one source run id.",
        ),
        work_type: str | None = typer.Option(
            None,
            "--work-type",
            help="Replay failed work items for one work type.",
        ),
        failure_class: str | None = typer.Option(
            None,
            "--failure-class",
            help="Replay failed work items for one durable failure class.",
        ),
        operator_note: str | None = typer.Option(
            None,
            "--note",
            help="Operator note recorded with the replay event.",
        ),
        limit: int = typer.Option(
            100,
            "--limit",
            min=1,
            help="Maximum number of failed work items to replay.",
        ),
    ) -> None:
        """Replay terminally failed facts-first work items through the admin API."""

        if not any(
            (
                work_item_id,
                repository_id,
                source_run_id,
                work_type,
                failure_class,
            )
        ):
            raise typer.BadParameter(
                "At least one selector is required: --work-item-id, "
                "--repository-id, --source-run-id, --work-type, or "
                "--failure-class."
            )

        run_remote_admin_facts_replay(
            main_module,
            service_url=service_url,
            api_key=api_key,
            profile=profile,
            work_item_ids=work_item_id,
            repository_id=repository_id,
            source_run_id=source_run_id,
            work_type=work_type,
            failure_class=failure_class,
            operator_note=operator_note,
            limit=limit,
        )
