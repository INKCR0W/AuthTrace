from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import datetime, timezone

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_app_settings, get_db_session
from app.core.config import Settings
from app.main import app
from app.models.account import Account
from app.models.account_event import AccountEvent
from app.models.account_snapshot import AccountSnapshot
from app.models.management_source import ManagementSource
from app.models.scan_job import ScanJob
from app.services.scan_scheduler import (
    AuthFileScanScheduler,
    SchedulerStatusSnapshot,
    build_scheduler_status_snapshot,
)


class FakeManagementClient:
    def __init__(
        self,
        *,
        auth_files: list[dict[str, object]],
        probe_results: dict[str, dict[str, object]],
        probe_errors: dict[str, Exception] | None = None,
    ) -> None:
        self.auth_files = auth_files
        self.probe_results = probe_results
        self.probe_errors = probe_errors or {}
        self.refresh_called = False

    async def refresh_config(self) -> None:
        self.refresh_called = True

    async def list_auth_files(self) -> list[dict[str, object]]:
        return self.auth_files

    async def probe_usage(
        self,
        *,
        auth_index: str,
        chatgpt_account_id: str | None = None,
    ) -> dict[str, object]:
        if auth_index in self.probe_errors:
            raise self.probe_errors[auth_index]
        return self.probe_results[auth_index]


def _create_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ManagementSource.__table__.create(engine)
    ScanJob.__table__.create(engine)
    Account.__table__.create(engine)
    AccountSnapshot.__table__.create(engine)
    AccountEvent.__table__.create(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


async def _request(method: str, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path)


def test_build_scheduler_status_snapshot_marks_blocked_when_config_missing() -> None:
    settings = Settings(
        AUTHTRACE_DATABASE_URL="sqlite+pysqlite:///:memory:",
        AUTHTRACE_SCHEDULER_ENABLED=True,
        AUTHTRACE_SCHEDULER_INTERVAL_MINUTES=10,
    )

    snapshot = build_scheduler_status_snapshot(settings)

    assert snapshot.enabled is True
    assert snapshot.running is False
    assert snapshot.interval_minutes == 10
    assert snapshot.last_status == "blocked"
    assert snapshot.last_error_message == "management source 配置不完整，自动扫描未启动"


def test_scan_scheduler_run_once_persists_scheduler_scan_job() -> None:
    session_factory = _create_session_factory()
    fake_client = FakeManagementClient(
        auth_files=[
            {
                "name": "Alpha",
                "auth_index": "auth-1",
                "type": "chatgpt",
                "provider": "openai",
                "disabled": False,
                "status": "active",
                "status_message": "ok",
                "chatgpt_account_id": "acct-alpha",
            }
        ],
        probe_results={
            "auth-1": {
                "status_code": 200,
                "body": {
                    "rate_limit": {
                        "individual_window": {
                            "used_percent": 67,
                            "reset_at": "2026-05-02T00:00:00Z",
                            "limit_window_seconds": 604800,
                            "remaining": 33,
                            "limit_reached": False,
                        },
                        "allowed": True,
                    }
                },
            }
        },
    )
    settings = Settings(
        AUTHTRACE_DATABASE_URL="sqlite+pysqlite:///:memory:",
        AUTHTRACE_MANAGEMENT_BASE_URL="http://localhost:8787",
        AUTHTRACE_MANAGEMENT_TOKEN="secret",
        AUTHTRACE_MANAGEMENT_TARGET_TYPE="chatgpt",
        AUTHTRACE_MANAGEMENT_PROVIDER="openai",
        AUTHTRACE_SCHEDULER_ENABLED=True,
        AUTHTRACE_SCHEDULER_INTERVAL_MINUTES=15,
    )
    scheduler = AuthFileScanScheduler(
        settings=settings,
        session_factory=session_factory,
        client_factory=lambda _: fake_client,
    )

    asyncio.run(scheduler.run_once())

    snapshot = scheduler.get_status_snapshot()
    assert snapshot.last_status == "success"
    assert snapshot.last_error_message is None
    assert snapshot.last_started_at is not None
    assert snapshot.last_finished_at is not None
    assert fake_client.refresh_called is True

    with session_factory() as db:
        scan_job = db.scalar(select(ScanJob))
        account = db.scalar(select(Account).where(Account.auth_index == "auth-1"))
        account_snapshot = db.scalar(select(AccountSnapshot))

        assert scan_job is not None
        assert scan_job.trigger_mode == "scheduler"
        assert scan_job.status == "success"
        assert scan_job.scanned_accounts == 1
        assert account is not None
        assert account.current_is_401 is False
        assert account_snapshot is not None
        assert account_snapshot.scan_job_id == scan_job.id


def test_scan_scheduler_run_once_keeps_partial_failed_status() -> None:
    session_factory = _create_session_factory()
    fake_client = FakeManagementClient(
        auth_files=[
            {
                "name": "Alpha",
                "auth_index": "auth-1",
                "type": "chatgpt",
                "provider": "openai",
                "disabled": False,
                "status": "active",
            },
            {
                "name": "Beta",
                "auth_index": "auth-2",
                "type": "chatgpt",
                "provider": "openai",
                "disabled": False,
                "status": "active",
            },
        ],
        probe_results={
            "auth-1": {
                "status_code": 200,
                "body": {
                    "rate_limit": {
                        "individual_window": {
                            "used_percent": 42,
                            "reset_at": "2026-05-02T00:00:00Z",
                            "limit_window_seconds": 604800,
                            "remaining": 58,
                            "limit_reached": False,
                        },
                        "allowed": True,
                    }
                },
            }
        },
        probe_errors={"auth-2": RuntimeError("probe timeout")},
    )
    settings = Settings(
        AUTHTRACE_DATABASE_URL="sqlite+pysqlite:///:memory:",
        AUTHTRACE_MANAGEMENT_BASE_URL="http://localhost:8787",
        AUTHTRACE_MANAGEMENT_TOKEN="secret",
        AUTHTRACE_MANAGEMENT_TARGET_TYPE="chatgpt",
        AUTHTRACE_MANAGEMENT_PROVIDER="openai",
        AUTHTRACE_SCHEDULER_ENABLED=True,
    )
    scheduler = AuthFileScanScheduler(
        settings=settings,
        session_factory=session_factory,
        client_factory=lambda _: fake_client,
    )

    asyncio.run(scheduler.run_once())

    snapshot = scheduler.get_status_snapshot()
    assert snapshot.last_status == "partial_failed"
    assert snapshot.last_error_message is None

    with session_factory() as db:
        scan_job = db.scalar(select(ScanJob))
        assert scan_job is not None
        assert scan_job.status == "partial_failed"
        assert scan_job.failed_accounts == 1


def test_scan_scheduler_run_once_skips_when_scan_job_is_already_running() -> None:
    session_factory = _create_session_factory()
    fake_client = FakeManagementClient(auth_files=[], probe_results={})
    settings = Settings(
        AUTHTRACE_DATABASE_URL="sqlite+pysqlite:///:memory:",
        AUTHTRACE_MANAGEMENT_BASE_URL="http://localhost:8787",
        AUTHTRACE_MANAGEMENT_TOKEN="secret",
        AUTHTRACE_SCHEDULER_ENABLED=True,
    )
    scheduler = AuthFileScanScheduler(
        settings=settings,
        session_factory=session_factory,
        client_factory=lambda _: fake_client,
    )

    with session_factory() as db:
        source = ManagementSource(
            source_key=settings.management_source_key,
            source_name=settings.management_source_name,
            base_url=settings.management_base_url or "",
            is_enabled=True,
        )
        db.add(source)
        db.flush()
        db.add(
            ScanJob(
                source_id=source.id,
                trigger_mode="manual",
                status="running",
                scan_started_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    asyncio.run(scheduler.run_once())

    snapshot = scheduler.get_status_snapshot()
    assert snapshot.last_status == "skipped_conflict"
    assert snapshot.last_error_message == "已有运行中的扫描任务 #1"

    with session_factory() as db:
        scan_jobs = db.scalars(select(ScanJob).order_by(ScanJob.id)).all()
        assert len(scan_jobs) == 1


def test_get_default_management_source_includes_scheduler_status() -> None:
    session_factory = _create_session_factory()
    settings = Settings(
        AUTHTRACE_DATABASE_URL="sqlite+pysqlite:///:memory:",
        AUTHTRACE_MANAGEMENT_BASE_URL="http://localhost:8787",
        AUTHTRACE_MANAGEMENT_TOKEN="secret",
        AUTHTRACE_SCHEDULER_ENABLED=True,
        AUTHTRACE_SCHEDULER_INTERVAL_MINUTES=20,
    )
    scheduler = AuthFileScanScheduler(settings=settings, session_factory=session_factory)
    scheduler.get_status_snapshot = lambda: SchedulerStatusSnapshot(
        enabled=True,
        running=True,
        interval_minutes=20,
        next_run_at=datetime(2026, 5, 2, 4, 30, tzinfo=timezone.utc),
        last_started_at=datetime(2026, 5, 2, 4, 0, tzinfo=timezone.utc),
        last_finished_at=datetime(2026, 5, 2, 4, 5, tzinfo=timezone.utc),
        last_status="success",
        last_error_message=None,
    )

    def override_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    previous_scheduler = getattr(app.state, "auth_file_scan_scheduler", None)
    app.state.auth_file_scan_scheduler = scheduler
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings

    response = asyncio.run(_request("GET", "/api/v1/management-sources/default"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["scheduler_enabled"] is True
    assert payload["scheduler_running"] is True
    assert payload["scheduler_interval_minutes"] == 20
    assert payload["scheduler_next_run_at"] == "2026-05-02T04:30:00Z"
    assert payload["scheduler_last_started_at"] == "2026-05-02T04:00:00Z"
    assert payload["scheduler_last_finished_at"] == "2026-05-02T04:05:00Z"
    assert payload["scheduler_last_status"] == "success"
    assert payload["scheduler_last_error_message"] is None

    app.dependency_overrides.clear()
    app.state.auth_file_scan_scheduler = previous_scheduler
