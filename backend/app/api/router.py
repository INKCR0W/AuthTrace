from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.management_sources import router as management_sources_router
from app.api.routes.sync import router as sync_router
from app.core.config import settings


api_router = APIRouter()
api_v1_router = APIRouter(prefix=settings.api_v1_prefix)

api_v1_router.include_router(health_router, prefix="/health", tags=["health"])
api_v1_router.include_router(
    management_sources_router,
    prefix="/management-sources",
    tags=["management-sources"],
)
api_v1_router.include_router(sync_router, prefix="/sync", tags=["sync"])
api_router.include_router(api_v1_router)
