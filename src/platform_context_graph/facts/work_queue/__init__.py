"""PostgreSQL-backed work queue contracts for fact projection."""

from .models import FactWorkItemRow
from .postgres import PostgresFactWorkQueue

__all__ = [
    "FactWorkItemRow",
    "PostgresFactWorkQueue",
]
