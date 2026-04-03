"""Repository graph projection helpers driven by stored facts."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from platform_context_graph.facts.storage.models import FactRecordRow

from .common import run_write_query


def _normalized_fact_type(fact_type: str) -> str:
    """Return a stable fact type name across transitional suffix variants."""

    return fact_type.removesuffix("Fact")


def iter_repository_facts(
    fact_records: Iterable[FactRecordRow],
) -> list[FactRecordRow]:
    """Return repository observation facts in stable insertion order."""

    seen_fact_ids: set[str] = set()
    repository_facts: list[FactRecordRow] = []
    for fact_record in fact_records:
        if _normalized_fact_type(fact_record.fact_type) != "RepositoryObserved":
            continue
        if fact_record.fact_id in seen_fact_ids:
            continue
        seen_fact_ids.add(fact_record.fact_id)
        repository_facts.append(fact_record)
    return repository_facts


def project_repository_facts(tx: object, fact_records: Iterable[FactRecordRow]) -> int:
    """Project repository facts into canonical Repository nodes."""

    projected = 0
    for fact_record in iter_repository_facts(fact_records):
        repo_path = str(Path(fact_record.checkout_path).resolve())
        run_write_query(
            tx,
            """
            MERGE (r:Repository {id: $repo_id})
            SET r.path = $repo_path,
                r.local_path = $local_path,
                r.name = $name,
                r.is_dependency = $is_dependency
            """,
            repo_id=fact_record.repository_id,
            repo_path=repo_path,
            local_path=repo_path,
            name=Path(repo_path).name,
            is_dependency=bool(fact_record.payload.get("is_dependency", False)),
        )
        projected += 1
    return projected


__all__ = [
    "iter_repository_facts",
    "project_repository_facts",
]
