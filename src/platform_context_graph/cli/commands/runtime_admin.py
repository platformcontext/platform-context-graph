"""Admin runtime command registration for the CLI entrypoint."""

from __future__ import annotations

from typing import Any

import typer

from ..remote_admin_facts import run_remote_admin_fact_backfill
from ..remote_admin_facts import run_remote_admin_fact_replay_events
from ..remote_admin_facts import run_remote_admin_facts_dead_letter
from ..remote_admin_facts import run_remote_admin_facts_list_decisions
from ..remote_admin_facts import run_remote_admin_facts_list_work_items
from ..remote_admin_facts import run_remote_admin_facts_replay
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

    @admin_facts_app.command("list")
    def admin_facts_list(
        service_url: str | None = typer.Option(None, "--service-url"),
        api_key: str | None = typer.Option(None, "--api-key"),
        profile: str | None = typer.Option(None, "--profile"),
        status: list[str] | None = typer.Option(
            None,
            "--status",
            help="Filter work items by status. Repeat for multiple values.",
        ),
        repository_id: str | None = typer.Option(None, "--repository-id"),
        source_run_id: str | None = typer.Option(None, "--source-run-id"),
        work_type: str | None = typer.Option(None, "--work-type"),
        failure_class: str | None = typer.Option(None, "--failure-class"),
        limit: int = typer.Option(100, "--limit", min=1),
    ) -> None:
        """List facts-first work items and their durable failure metadata."""

        run_remote_admin_facts_list_work_items(
            main_module,
            service_url=service_url,
            api_key=api_key,
            profile=profile,
            statuses=status,
            repository_id=repository_id,
            source_run_id=source_run_id,
            work_type=work_type,
            failure_class=failure_class,
            limit=limit,
        )

    @admin_facts_app.command("decisions")
    def admin_facts_decisions(
        repository_id: str = typer.Option(..., "--repository-id"),
        source_run_id: str = typer.Option(..., "--source-run-id"),
        service_url: str | None = typer.Option(None, "--service-url"),
        api_key: str | None = typer.Option(None, "--api-key"),
        profile: str | None = typer.Option(None, "--profile"),
        decision_type: str | None = typer.Option(None, "--decision-type"),
        include_evidence: bool = typer.Option(
            False,
            "--include-evidence/--no-include-evidence",
        ),
        limit: int = typer.Option(100, "--limit", min=1),
    ) -> None:
        """List persisted projection decisions and optional evidence."""

        run_remote_admin_facts_list_decisions(
            main_module,
            service_url=service_url,
            api_key=api_key,
            profile=profile,
            repository_id=repository_id,
            source_run_id=source_run_id,
            decision_type=decision_type,
            include_evidence=include_evidence,
            limit=limit,
        )

    @admin_facts_app.command("dead-letter")
    def admin_facts_dead_letter(
        service_url: str | None = typer.Option(None, "--service-url"),
        api_key: str | None = typer.Option(None, "--api-key"),
        profile: str | None = typer.Option(None, "--profile"),
        work_item_id: list[str] | None = typer.Option(None, "--work-item-id"),
        repository_id: str | None = typer.Option(None, "--repository-id"),
        source_run_id: str | None = typer.Option(None, "--source-run-id"),
        work_type: str | None = typer.Option(None, "--work-type"),
        failure_class: str = typer.Option("manual_override", "--failure-class"),
        operator_note: str | None = typer.Option(None, "--note"),
        limit: int = typer.Option(100, "--limit", min=1),
    ) -> None:
        """Dead-letter selected facts-first work items through the admin API."""

        if not any((work_item_id, repository_id, source_run_id, work_type)):
            raise typer.BadParameter(
                "At least one selector is required: --work-item-id, "
                "--repository-id, --source-run-id, or --work-type."
            )
        run_remote_admin_facts_dead_letter(
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

    @admin_facts_app.command("backfill")
    def admin_facts_backfill(
        service_url: str | None = typer.Option(None, "--service-url"),
        api_key: str | None = typer.Option(None, "--api-key"),
        profile: str | None = typer.Option(None, "--profile"),
        repository_id: str | None = typer.Option(None, "--repository-id"),
        source_run_id: str | None = typer.Option(None, "--source-run-id"),
        operator_note: str | None = typer.Option(None, "--note"),
    ) -> None:
        """Create a durable fact backfill request through the admin API."""

        if not any((repository_id, source_run_id)):
            raise typer.BadParameter(
                "At least one selector is required: --repository-id or --source-run-id."
            )
        run_remote_admin_fact_backfill(
            main_module,
            service_url=service_url,
            api_key=api_key,
            profile=profile,
            repository_id=repository_id,
            source_run_id=source_run_id,
            operator_note=operator_note,
        )

    @admin_facts_app.command("replay-events")
    def admin_facts_replay_events(
        service_url: str | None = typer.Option(None, "--service-url"),
        api_key: str | None = typer.Option(None, "--api-key"),
        profile: str | None = typer.Option(None, "--profile"),
        repository_id: str | None = typer.Option(None, "--repository-id"),
        source_run_id: str | None = typer.Option(None, "--source-run-id"),
        work_item_id: str | None = typer.Option(None, "--work-item-id"),
        failure_class: str | None = typer.Option(None, "--failure-class"),
        limit: int = typer.Option(100, "--limit", min=1),
    ) -> None:
        """List durable replay-event audit rows through the admin API."""

        run_remote_admin_fact_replay_events(
            main_module,
            service_url=service_url,
            api_key=api_key,
            profile=profile,
            repository_id=repository_id,
            source_run_id=source_run_id,
            work_item_id=work_item_id,
            failure_class=failure_class,
            limit=limit,
        )
