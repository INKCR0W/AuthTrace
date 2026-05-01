from __future__ import annotations

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
def root_health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}

