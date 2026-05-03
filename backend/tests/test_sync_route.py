from __future__ import annotations

import asyncio
from collections.abc import Generator

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_app_settings, get_db_session, get_management_client
from app.clients.management import ManagementApiError
from app.core.config import Settings
from app.main import app
from app.models.management_source import ManagementSource
from app.models.scan_job import ScanJob


class FailingManagementClient:
    async def refresh_config(self) -> None:
        raise ManagementApiError("management request transport error: GET /v0/management/config.yaml -> failed")


def _create_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ManagementSource.__table__.create(engine)
    ScanJob.__table__.create(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


async def _request(method: str, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path)


def test_sync_auth_files_returns_bad_gateway_when_management_is_unreachable() -> None:
    session_factory = _create_session_factory()
    settings = Settings(
        AUTHTRACE_DATABASE_URL="sqlite+pysqlite:///:memory:",
        AUTHTRACE_MANAGEMENT_BASE_URL="http://host.docker.internal:8787",
        AUTHTRACE_MANAGEMENT_TOKEN="secret",
    )

    def override_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_management_client] = lambda: FailingManagementClient()

    try:
        response = asyncio.run(_request("POST", "/api/v1/sync/auth-files"))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    payload = response.json()
    expected_message = "管理端请求失败，请确认 AUTHTRACE_MANAGEMENT_BASE_URL 在后端容器内可访问"
    assert payload["detail"]["message"] == expected_message
    assert "transport error" in payload["detail"]["error"]
