from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.schemas.dashboard import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def health_check(request: Request) -> HealthResponse:
    settings = get_settings()
    db_ready = getattr(request.app.state, "db_ready", False)
    database_error = getattr(request.app.state, "database_error", None)
    return HealthResponse(
        status="ok" if db_ready else "degraded",
        app_name=settings.app_name,
        database_url=settings.database_url,
        db_ready=db_ready,
        database_error=database_error,
    )
