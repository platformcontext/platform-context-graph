"""HTTP routes for orchestrated service investigations."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...domain.responses import InvestigationResponse
from ..dependencies import QueryServices, get_query_services

router = APIRouter(prefix="/investigations", tags=["investigations"])


@router.get(
    "/services/{service_name}",
    response_model=InvestigationResponse,
    response_model_exclude_none=True,
)
def investigate_service(
    service_name: str,
    environment: str | None = None,
    intent: str | None = None,
    question: str | None = None,
    services: QueryServices = Depends(get_query_services),
) -> dict[str, object]:
    """Return an orchestrated investigation for one service."""

    return services.investigation.investigate_service(
        services.database,
        service_name=service_name,
        environment=environment,
        intent=intent,
        question=question,
    )
