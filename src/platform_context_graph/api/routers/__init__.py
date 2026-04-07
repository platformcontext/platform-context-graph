"""Router exports used to assemble the public HTTP API."""

from __future__ import annotations

from .code import router as code_router
from .content import router as content_router
from .entities import router as entities_router
from .environments import router as environments_router
from .impact import router as impact_router
from .infra import router as infra_router
from .investigations import router as investigations_router
from .paths import router as paths_router
from .repositories import router as repositories_router
from .services import router as services_router
from .traces import router as traces_router
from .workloads import router as workloads_router
from .admin import router as admin_router
from .admin_facts import router as admin_facts_router

__all__ = [
    "admin_facts_router",
    "admin_router",
    "code_router",
    "content_router",
    "entities_router",
    "environments_router",
    "impact_router",
    "infra_router",
    "investigations_router",
    "paths_router",
    "repositories_router",
    "services_router",
    "traces_router",
    "workloads_router",
]
