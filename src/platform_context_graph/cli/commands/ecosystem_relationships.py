"""Store-backed ecosystem relationship review commands."""

from __future__ import annotations

import json
from typing import Any

import typer

from platform_context_graph.observability import get_observability
from platform_context_graph.relationships import (
    REPOSITORY_DEPENDENCY_SCOPE,
    RelationshipAssertion,
    get_relationship_store,
)
from platform_context_graph.utils.debug_log import emit_log_call, info_logger


def _require_relationship_store() -> Any:
    """Return the configured relationship store or raise a CLI error."""

    store = get_relationship_store()
    if store is None or not store.enabled:
        typer.echo(
            "Relationship store is not configured. Set "
            "PCG_RELATIONSHIP_STORE_DSN, PCG_CONTENT_STORE_DSN, or "
            "PCG_POSTGRES_DSN.",
            err=True,
        )
        raise typer.Exit(1)
    return store


def _start_cli_span(command_name: str, **attributes: object) -> Any:
    """Start one relationship CLI span using the shared runtime component."""

    observability = get_observability()
    return observability.start_span(
        f"pcg.relationships.cli.{command_name}",
        component=observability.component,
        attributes={
            "pcg.relationships.scope": REPOSITORY_DEPENDENCY_SCOPE,
            **attributes,
        },
    )


def register_ecosystem_relationship_commands(
    main_module: Any,
    ecosystem_app: typer.Typer,
) -> None:
    """Register relationship review commands on the ecosystem CLI group."""

    _ = main_module

    @ecosystem_app.command("generation")
    def ecosystem_generation() -> None:
        """Show the active relationship resolution generation."""

        with _start_cli_span("generation"):
            store = _require_relationship_store()
            generation = store.get_active_generation(scope=REPOSITORY_DEPENDENCY_SCOPE)
            if generation is None:
                typer.echo("No active relationship generation.")
                return
            emit_log_call(
                info_logger,
                "Loaded active relationship generation",
                event_name="relationships.cli.generation.loaded",
                extra_keys={
                    "scope": generation.scope,
                    "generation_id": generation.generation_id,
                    "run_id": generation.run_id or "adhoc",
                    "status": generation.status,
                },
            )
            typer.echo(
                json.dumps(
                    {
                        "generation_id": generation.generation_id,
                        "scope": generation.scope,
                        "run_id": generation.run_id,
                        "status": generation.status,
                    },
                    sort_keys=True,
                )
            )

    @ecosystem_app.command("relationships")
    def ecosystem_relationships() -> None:
        """List resolved repository relationships from the active generation."""

        with _start_cli_span("relationships"):
            store = _require_relationship_store()
            generation = store.get_active_generation(scope=REPOSITORY_DEPENDENCY_SCOPE)
            relationships = store.list_resolved_relationships(
                scope=REPOSITORY_DEPENDENCY_SCOPE
            )
            if generation is None:
                typer.echo("No active relationship generation.")
                return
            emit_log_call(
                info_logger,
                "Listed resolved repository relationships",
                event_name="relationships.cli.relationships.listed",
                extra_keys={
                    "scope": generation.scope,
                    "generation_id": generation.generation_id,
                    "run_id": generation.run_id or "adhoc",
                    "relationship_count": len(relationships),
                },
            )
            typer.echo(
                f"Active generation: {generation.generation_id} "
                f"(scope={generation.scope}, run_id={generation.run_id or 'adhoc'})"
            )
            if not relationships:
                typer.echo("No resolved relationships.")
                return
            for relationship in relationships:
                typer.echo(
                    "\t".join(
                        [
                            relationship.source_repo_id,
                            relationship.relationship_type,
                            relationship.target_repo_id,
                            f"{relationship.confidence:.2f}",
                            str(relationship.evidence_count),
                            relationship.resolution_source,
                        ]
                    )
                )

    @ecosystem_app.command("candidates")
    def ecosystem_candidates(
        relationship_type: str | None = typer.Option(
            None,
            "--relationship-type",
            help="Optional relationship type to filter candidates.",
        ),
    ) -> None:
        """List active relationship candidates before assertion/rejection review."""

        with _start_cli_span("candidates"):
            store = _require_relationship_store()
            candidates = store.list_relationship_candidates(
                scope=REPOSITORY_DEPENDENCY_SCOPE,
                relationship_type=relationship_type,
            )
            emit_log_call(
                info_logger,
                "Listed active relationship candidates",
                event_name="relationships.cli.candidates.listed",
                extra_keys={
                    "scope": REPOSITORY_DEPENDENCY_SCOPE,
                    "candidate_count": len(candidates),
                    "relationship_type": relationship_type or "all",
                },
            )
            if not candidates:
                typer.echo("No active relationship candidates.")
                return
            for candidate in candidates:
                typer.echo(
                    "\t".join(
                        [
                            candidate.source_repo_id,
                            candidate.relationship_type,
                            candidate.target_repo_id,
                            f"{candidate.confidence:.2f}",
                            str(candidate.evidence_count),
                        ]
                    )
                )

    @ecosystem_app.command("assert-relationship")
    def ecosystem_assert_relationship(
        source_repo_id: str = typer.Argument(
            ..., help="Canonical source repository ID."
        ),
        target_repo_id: str = typer.Argument(
            ..., help="Canonical target repository ID."
        ),
        reason: str = typer.Option(
            ..., "--reason", help="Why the relationship is valid."
        ),
        actor: str = typer.Option(
            "cli", "--actor", help="Actor recording the assertion."
        ),
        relationship_type: str = typer.Option(
            "DEPENDS_ON",
            "--relationship-type",
            help="Relationship type to assert.",
        ),
    ) -> None:
        """Persist an explicit repository dependency assertion."""

        with _start_cli_span(
            "assert_relationship",
            **{"pcg.relationships.decision": "assert"},
        ):
            store = _require_relationship_store()
            store.upsert_relationship_assertion(
                RelationshipAssertion(
                    source_repo_id=source_repo_id,
                    target_repo_id=target_repo_id,
                    relationship_type=relationship_type,
                    decision="assert",
                    reason=reason,
                    actor=actor,
                )
            )
            emit_log_call(
                info_logger,
                "Stored repository relationship assertion from CLI",
                event_name="relationships.cli.assertion.stored",
                extra_keys={
                    "scope": REPOSITORY_DEPENDENCY_SCOPE,
                    "decision": "assert",
                    "relationship_type": relationship_type,
                    "actor": actor,
                    "source_repo_id": source_repo_id,
                    "target_repo_id": target_repo_id,
                },
            )
            typer.echo(
                f"Stored assert {relationship_type} for {source_repo_id} -> {target_repo_id}"
            )

    @ecosystem_app.command("reject-relationship")
    def ecosystem_reject_relationship(
        source_repo_id: str = typer.Argument(
            ..., help="Canonical source repository ID."
        ),
        target_repo_id: str = typer.Argument(
            ..., help="Canonical target repository ID."
        ),
        reason: str = typer.Option(
            ..., "--reason", help="Why the relationship should be blocked."
        ),
        actor: str = typer.Option(
            "cli", "--actor", help="Actor recording the rejection."
        ),
        relationship_type: str = typer.Option(
            "DEPENDS_ON",
            "--relationship-type",
            help="Relationship type to reject.",
        ),
    ) -> None:
        """Persist an explicit repository dependency rejection."""

        with _start_cli_span(
            "reject_relationship",
            **{"pcg.relationships.decision": "reject"},
        ):
            store = _require_relationship_store()
            store.upsert_relationship_assertion(
                RelationshipAssertion(
                    source_repo_id=source_repo_id,
                    target_repo_id=target_repo_id,
                    relationship_type=relationship_type,
                    decision="reject",
                    reason=reason,
                    actor=actor,
                )
            )
            emit_log_call(
                info_logger,
                "Stored repository relationship rejection from CLI",
                event_name="relationships.cli.assertion.stored",
                extra_keys={
                    "scope": REPOSITORY_DEPENDENCY_SCOPE,
                    "decision": "reject",
                    "relationship_type": relationship_type,
                    "actor": actor,
                    "source_repo_id": source_repo_id,
                    "target_repo_id": target_repo_id,
                },
            )
            typer.echo(
                f"Stored reject {relationship_type} for {source_repo_id} -> {target_repo_id}"
            )
