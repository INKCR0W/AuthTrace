from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import datetime, timezone

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_app_settings, get_db_session, get_management_client
from app.core.config import Settings
from app.main import app
from app.models.account import Account
from app.models.management_source import ManagementSource
from app.models.scan_job import ScanJob


class FakeManagementClient:
    def __init__(self, auth_files: list[dict[str, object]]) -> None:
        self.auth_files = auth_files
        self.refresh_called = False

    async def refresh_config(self) -> None:
        self.refresh_called = True

    async def list_auth_files(self) -> list[dict[str, object]]:
        return self.auth_files


def _create_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ManagementSource.__table__.create(engine)
    ScanJob.__table__.create(engine)
    Account.__table__.create(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


async def _request(
    method: str,
    path: str,
    *,
    json: dict[str, object] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, json=json)


def test_get_default_management_source_without_config() -> None:
    session_factory = _create_session_factory()

    def override_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: Settings(
        AUTHTRACE_DATABASE_URL="sqlite+pysqlite:///:memory:"
    )

    response = asyncio.run(_request("GET", "/api/v1/management-sources/default"))

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["source_id"] is None

    app.dependency_overrides.clear()


def test_sync_auth_files_persists_accounts_and_scan_job() -> None:
    session_factory = _create_session_factory()
    fake_client = FakeManagementClient(
        [
            {
                "name": "Alpha",
                "auth_index": "auth-1",
                "type": "chatgpt",
                "provider": "openai",
                "disabled": False,
                "status": "active",
                "status_message": "ok",
                "email": "alpha@example.com",
            },
            {
                "name": "Beta",
                "auth_index": "auth-2",
                "type": "chatgpt",
                "provider": "openai",
                "disabled": True,
                "status": "active",
                "status_message": {"reason": "manual"},
            },
            {
                "name": "MissingIndex",
                "type": "chatgpt",
                "provider": "openai",
            },
        ]
    )

    def override_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    settings = Settings(
        AUTHTRACE_DATABASE_URL="sqlite+pysqlite:///:memory:",
        AUTHTRACE_MANAGEMENT_BASE_URL="http://localhost:8787",
        AUTHTRACE_MANAGEMENT_TOKEN="secret",
        AUTHTRACE_MANAGEMENT_TARGET_TYPE="chatgpt",
        AUTHTRACE_MANAGEMENT_PROVIDER="openai",
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_management_client] = lambda: fake_client

    with session_factory() as db:
        seen_at = datetime.now(timezone.utc)
        source = ManagementSource(
            source_key=settings.management_source_key,
            source_name=settings.management_source_name,
            base_url=settings.management_base_url or "",
            is_enabled=True,
        )
        db.add(source)
        db.flush()
        db.add(
            Account(
                source_id=source.id,
                auth_index="old-auth",
                name="Old",
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
        )
        db.commit()

    response = asyncio.run(
        _request(
            "POST",
            "/api/v1/sync/auth-files",
            json={"trigger_mode": "manual"},
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["total_accounts"] == 3
    assert payload["synced_accounts"] == 2
    assert payload["eligible_accounts"] == 1
    assert payload["skipped_accounts"] == 1
    assert payload["missing_auth_index_accounts"] == 1
    assert fake_client.refresh_called is True

    with session_factory() as db:
        scan_job = db.scalar(select(ScanJob).where(ScanJob.id == payload["scan_job_id"]))
        assert scan_job is not None
        assert scan_job.status == "success"
        assert scan_job.total_accounts == 3
        assert scan_job.eligible_accounts == 1
        assert scan_job.success_accounts == 2
        assert scan_job.failed_accounts == 1

        alpha = db.scalar(select(Account).where(Account.auth_index == "auth-1"))
        beta = db.scalar(select(Account).where(Account.auth_index == "auth-2"))
        old = db.scalar(select(Account).where(Account.auth_index == "old-auth"))

        assert alpha is not None
        assert alpha.name == "Alpha"
        assert alpha.source_deleted_at is None
        assert beta is not None
        assert beta.disabled is True
        assert beta.status_message == '{"reason": "manual"}'
        assert old is not None
        assert old.source_deleted_at is not None

    app.dependency_overrides.clear()
