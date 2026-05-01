from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.services.scan_scheduler import AuthFileScanScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.auth_file_scan_scheduler.start()
    try:
        yield
    finally:
        app.state.auth_file_scan_scheduler.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_allowed_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router)
    app.state.auth_file_scan_scheduler = AuthFileScanScheduler(settings=settings)

    @app.get("/health", tags=["system"])
    def root_health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    return app


app = create_app()
