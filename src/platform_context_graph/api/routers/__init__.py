"""Router exports used to assemble the public HTTP API."""

from __future__ import annotations

from .admin import router as admin_router

__all__ = [
    "admin_router",
]
