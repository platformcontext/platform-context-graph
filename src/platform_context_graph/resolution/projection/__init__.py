"""Fact-driven graph projection helpers for the Resolution Engine."""

from __future__ import annotations

from typing import Iterable

from platform_context_graph.facts.storage.models import FactRecordRow

from .common import run_managed_write
from .entities import project_parsed_entity_facts
from .files import project_file_facts
from .repositories import project_repository_facts


def project_git_fact_records(
    *,
    builder: object,
    fact_records: Iterable[FactRecordRow],
    warning_logger_fn: object | None = None,
) -> dict[str, int]:
    """Project repository, file, and entity graph state from Git fact records."""

    records = list(fact_records)

    def _write(tx: object) -> None:
        """Execute projection writes inside one managed graph transaction."""

        project_repository_facts(tx, records)
        project_file_facts(tx, records, warning_logger_fn=warning_logger_fn)
        project_parsed_entity_facts(tx, records)

    with builder.driver.session() as session:
        run_managed_write(session, _write)

    return {
        "repositories": len(
            [record for record in records if record.fact_type.startswith("Repository")]
        ),
        "files": len(
            [record for record in records if record.fact_type.startswith("File")]
        ),
        "entities": len(
            [
                record
                for record in records
                if record.fact_type.startswith("ParsedEntity")
            ]
        ),
    }


__all__ = [
    "project_git_fact_records",
    "project_repository_facts",
    "project_file_facts",
    "project_parsed_entity_facts",
]
