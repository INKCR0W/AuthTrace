from __future__ import annotations

from fastapi import APIRouter

from app.schemas.health import HealthResponse


router = APIRouter()


@router.get("", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok", service="api")

