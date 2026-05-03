from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_app_settings, get_db_session, get_management_client
from app.api.serializers import LEGACY_BLANK_ERROR_MESSAGE
from app.core.config import Settings
from app.main import app
from app.models.account import Account
from app.models.account_event import AccountEvent
from app.models.account_snapshot import AccountSnapshot
from app.models.management_source import ManagementSource
from app.models.scan_job import ScanJob
from app.services.auth_file_sync import run_auth_file_sync


class FakeManagementClient:
    def __init__(
        self,
        auth_files: list[dict[str, object]],
        probe_results: dict[str, dict[str, object]] | None = None,
        probe_errors: dict[str, Exception] | None = None,
        probe_delay_seconds: float = 0.0,
        refresh_error: Exception | None = None,
    ) -> None:
        self.auth_files = auth_files
        self.probe_results = probe_results or {}
        self.probe_errors = probe_errors or {}
        self.probe_delay_seconds = probe_delay_seconds
        self.refresh_error = refresh_error
        self.refresh_called = False
        self.probe_calls: list[tuple[str, str | None]] = []
        self.current_inflight_probes = 0
        self.max_inflight_probes = 0

    async def refresh_config(self) -> None:
        self.refresh_called = True
        if self.refresh_error is not None:
            raise self.refresh_error

    async def list_auth_files(self) -> list[dict[str, object]]:
        return self.auth_files

    async def probe_usage(
        self,
        *,
        auth_index: str,
        chatgpt_account_id: str | None = None,
    ) -> dict[str, object]:
        self.probe_calls.append((auth_index, chatgpt_account_id))
        self.current_inflight_probes += 1
        self.max_inflight_probes = max(self.max_inflight_probes, self.current_inflight_probes)
        try:
            if self.probe_delay_seconds > 0:
                await asyncio.sleep(self.probe_delay_seconds)
            if auth_index in self.probe_errors:
                raise self.probe_errors[auth_index]
            return self.probe_results[auth_index]
        finally:
            self.current_inflight_probes -= 1


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


async def _request(
    method: str,
    path: str,
    *,
    json: dict[str, object] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
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
        auth_files=[
            {
                "name": "Alpha",
                "auth_index": "auth-1",
                "type": "chatgpt",
                "provider": "openai",
                "disabled": False,
                "status": "active",
                "status_message": "ok",
                "email": "alpha@example.com",
                "chatgpt_account_id": "acct-alpha",
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
        ],
        probe_results={
            "auth-1": {
                "status_code": 200,
                "body": {
                    "rate_limit": {
                        "individual_window": {
                            "used_percent": 91,
                            "reset_at": "2026-05-02T00:00:00Z",
                            "limit_window_seconds": 604800,
                            "remaining": 9,
                            "limit_reached": False,
                        },
                        "secondary_window": {
                            "used_percent": 55,
                            "reset_at": "2026-05-01T23:00:00Z",
                            "limit_window_seconds": 18000,
                            "remaining": 45,
                            "limit_reached": False,
                        },
                        "allowed": True,
                    }
                },
            }
        },
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
    assert payload["scanned_accounts"] == 1
    assert payload["successful_snapshots"] == 1
    assert payload["failed_snapshots"] == 0
    assert fake_client.refresh_called is True
    assert fake_client.probe_calls == [("auth-1", "acct-alpha")]

    with session_factory() as db:
        scan_job = db.scalar(select(ScanJob).where(ScanJob.id == payload["scan_job_id"]))
        assert scan_job is not None
        assert scan_job.status == "success"
        assert scan_job.total_accounts == 3
        assert scan_job.eligible_accounts == 1
        assert scan_job.scanned_accounts == 1
        assert scan_job.success_accounts == 1
        assert scan_job.failed_accounts == 0

        alpha = db.scalar(select(Account).where(Account.auth_index == "auth-1"))
        beta = db.scalar(select(Account).where(Account.auth_index == "auth-2"))
        old = db.scalar(select(Account).where(Account.auth_index == "old-auth"))
        snapshots = db.scalars(select(AccountSnapshot).order_by(AccountSnapshot.account_id)).all()

        assert alpha is not None
        assert alpha.name == "Alpha"
        assert alpha.source_deleted_at is None
        assert alpha.current_status_code == 200
        assert alpha.current_is_401 is False
        assert str(alpha.current_weekly_used_percent) == "91.00"
        assert str(alpha.current_short_used_percent) == "55.00"
        assert alpha.current_invalid_quota is False
        assert beta is not None
        assert beta.disabled is True
        assert beta.status_message == '{"reason": "manual"}'
        assert beta.current_status_code is None
        assert old is not None
        assert old.source_deleted_at is not None
        assert len(snapshots) == 1
        assert snapshots[0].snapshot_status == "success"
        assert snapshots[0].probe_status_code == 200
        assert snapshots[0].raw_usage_json is not None

    app.dependency_overrides.clear()


def test_sync_auth_files_limits_probe_concurrency() -> None:
    session_factory = _create_session_factory()
    fake_client = FakeManagementClient(
        auth_files=[
            {
                "name": f"Alpha-{index}",
                "auth_index": f"auth-{index}",
                "type": "chatgpt",
                "provider": "openai",
                "disabled": False,
                "status": "active",
                "status_message": "ok",
            }
            for index in range(1, 6)
        ],
        probe_results={
            f"auth-{index}": {
                "status_code": 200,
                "body": {
                    "rate_limit": {
                        "individual_window": {
                            "used_percent": 40 + index,
                            "reset_at": "2026-05-02T00:00:00Z",
                            "limit_window_seconds": 604800,
                            "remaining": 100 - index,
                            "limit_reached": False,
                        },
                        "allowed": True,
                    }
                },
            }
            for index in range(1, 6)
        },
        probe_delay_seconds=0.01,
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
        AUTHTRACE_MANAGEMENT_PROBE_CONCURRENCY=2,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_management_client] = lambda: fake_client

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
    assert payload["scanned_accounts"] == 5
    assert payload["successful_snapshots"] == 5
    assert fake_client.max_inflight_probes == 2

    with session_factory() as db:
        scan_job = db.scalar(select(ScanJob).where(ScanJob.id == payload["scan_job_id"]))
        snapshots = db.scalars(select(AccountSnapshot).order_by(AccountSnapshot.id)).all()

        assert scan_job is not None
        assert scan_job.status == "success"
        assert scan_job.scanned_accounts == 5
        assert scan_job.success_accounts == 5
        assert len(snapshots) == 5

    app.dependency_overrides.clear()


def test_sync_auth_files_persists_running_progress_during_delayed_probes() -> None:
    session_factory = _create_session_factory()
    fake_client = FakeManagementClient(
        auth_files=[
            {
                "name": f"Alpha-{index}",
                "auth_index": f"auth-{index}",
                "type": "chatgpt",
                "provider": "openai",
                "disabled": False,
                "status": "active",
            }
            for index in range(1, 6)
        ],
        probe_results={
            f"auth-{index}": {
                "status_code": 200,
                "body": {
                    "rate_limit": {
                        "individual_window": {
                            "used_percent": 40 + index,
                            "reset_at": "2026-05-02T00:00:00Z",
                            "limit_window_seconds": 604800,
                            "remaining": 100 - index,
                            "limit_reached": False,
                        },
                        "allowed": True,
                    }
                },
            }
            for index in range(1, 6)
        },
        probe_delay_seconds=0.05,
    )
    settings = Settings(
        AUTHTRACE_DATABASE_URL="sqlite+pysqlite:///:memory:",
        AUTHTRACE_MANAGEMENT_BASE_URL="http://localhost:8787",
        AUTHTRACE_MANAGEMENT_TOKEN="secret",
        AUTHTRACE_MANAGEMENT_PROBE_CONCURRENCY=1,
    )

    async def run_and_observe_progress() -> tuple[bool, bool]:
        with session_factory() as run_db:
            task = asyncio.create_task(
                run_auth_file_sync(
                    run_db,
                    settings=settings,
                    client=fake_client,
                    trigger_mode="manual",
                )
            )
            saw_account_totals = False
            saw_partial_probe_progress = False

            for _ in range(100):
                await asyncio.sleep(0.01)
                with session_factory() as inspect_db:
                    scan_job = inspect_db.scalar(select(ScanJob).order_by(ScanJob.id.desc()).limit(1))
                    if scan_job is None or scan_job.status != "running":
                        continue
                    if scan_job.total_accounts == 5 and scan_job.eligible_accounts == 5:
                        saw_account_totals = True
                    if 0 < scan_job.scanned_accounts < 5:
                        saw_partial_probe_progress = True
                if saw_account_totals and saw_partial_probe_progress:
                    break

            response = await task
            assert response.scanned_accounts == 5
            return saw_account_totals, saw_partial_probe_progress

    saw_account_totals, saw_partial_probe_progress = asyncio.run(run_and_observe_progress())

    assert saw_account_totals is True
    assert saw_partial_probe_progress is True


def test_sync_auth_files_rejects_when_running_scan_job_exists() -> None:
    session_factory = _create_session_factory()
    fake_client = FakeManagementClient(auth_files=[])

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
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_management_client] = lambda: fake_client

    with session_factory() as db:
        started_at = datetime.now(timezone.utc).replace(microsecond=0)
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
                trigger_mode="scheduler",
                status="running",
                scan_started_at=started_at,
            )
        )
        db.commit()

    response = asyncio.run(_request("POST", "/api/v1/sync/auth-files", json={"trigger_mode": "manual"}))

    assert response.status_code == 409
    payload = response.json()
    assert payload["detail"]["message"] == "当前已有进行中的扫描任务"
    assert payload["detail"]["running_scan_job_id"] == 1
    assert payload["detail"]["source_id"] == 1
    assert payload["detail"]["scan_started_at"].startswith(started_at.strftime("%Y-%m-%dT%H:%M:%S"))
    assert fake_client.refresh_called is False
    assert fake_client.probe_calls == []

    with session_factory() as db:
        scan_jobs = db.scalars(select(ScanJob).order_by(ScanJob.id)).all()
        assert len(scan_jobs) == 1
        assert scan_jobs[0].status == "running"

    app.dependency_overrides.clear()


def test_sync_auth_files_returns_conflict_when_running_job_is_created_concurrently() -> None:
    session_factory = _create_session_factory()
    fake_client = FakeManagementClient(auth_files=[])

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
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_management_client] = lambda: fake_client

    with session_factory() as db:
        source = ManagementSource(
            source_key=settings.management_source_key,
            source_name=settings.management_source_name,
            base_url=settings.management_base_url or "",
            is_enabled=True,
        )
        db.add(source)
        db.commit()

    conflicting_started_at = datetime.now(timezone.utc).replace(microsecond=0)

    def raise_conflict(*args: object, **kwargs: object) -> None:
        with session_factory() as db:
            source = db.scalar(select(ManagementSource).where(ManagementSource.source_key == settings.management_source_key))
            assert source is not None
            db.add(
                ScanJob(
                    source_id=source.id,
                    trigger_mode="scheduler",
                    status="running",
                    scan_started_at=conflicting_started_at,
                )
            )
            db.commit()
        raise IntegrityError("insert into scan_jobs", {}, RuntimeError("duplicate running job"))

    with patch("app.services.auth_file_sync.create_scan_job", side_effect=raise_conflict):
        response = asyncio.run(_request("POST", "/api/v1/sync/auth-files", json={"trigger_mode": "manual"}))

    assert response.status_code == 409
    payload = response.json()
    assert payload["detail"]["message"] == "当前已有进行中的扫描任务"
    assert payload["detail"]["running_scan_job_id"] == 1
    assert payload["detail"]["source_id"] == 1
    assert payload["detail"]["scan_started_at"].startswith(conflicting_started_at.strftime("%Y-%m-%dT%H:%M:%S"))
    assert fake_client.refresh_called is False
    assert fake_client.probe_calls == []

    with session_factory() as db:
        scan_jobs = db.scalars(select(ScanJob).order_by(ScanJob.id)).all()
        assert len(scan_jobs) == 1
        assert scan_jobs[0].status == "running"

    app.dependency_overrides.clear()


def test_failed_probe_does_not_override_previous_current_state() -> None:
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
            }
        ],
        probe_errors={"auth-1": RuntimeError("probe timeout")},
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
                auth_index="auth-1",
                name="Alpha",
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                current_status_code=200,
                current_is_401=False,
                current_invalid_quota=False,
                current_last_checked_at=seen_at,
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
    assert payload["status"] == "partial_failed"
    assert payload["failed_snapshots"] == 1

    with session_factory() as db:
        account = db.scalar(select(Account).where(Account.auth_index == "auth-1"))
        assert account is not None
        snapshot = db.scalar(select(AccountSnapshot).where(AccountSnapshot.account_id == account.id))
        assert account.current_status_code == 200
        assert account.current_is_401 is False
        assert snapshot is not None
        assert snapshot.snapshot_status == "failed"
        assert snapshot.error_message == "probe timeout"

    app.dependency_overrides.clear()


def test_sync_auth_files_records_fallback_error_message_for_blank_exception() -> None:
    session_factory = _create_session_factory()
    fake_client = FakeManagementClient(
        auth_files=[],
        refresh_error=RuntimeError(),
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
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_management_client] = lambda: fake_client

    response = asyncio.run(
        _request(
            "POST",
            "/api/v1/sync/auth-files",
            json={"trigger_mode": "manual"},
        )
    )

    assert response.status_code == 500

    with session_factory() as db:
        scan_job = db.scalar(select(ScanJob))
        assert scan_job is not None
        assert scan_job.status == "failed"
        assert scan_job.error_message == "RuntimeError（未提供错误详情）"

    app.dependency_overrides.clear()


def test_401_probe_clears_stale_quota_current_state() -> None:
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
            }
        ],
        probe_results={"auth-1": {"status_code": 401, "body": {"detail": "unauthorized"}}},
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
                auth_index="auth-1",
                name="Alpha",
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                current_status_code=200,
                current_is_401=False,
                current_invalid_quota=True,
                current_remaining=12,
                current_last_checked_at=seen_at,
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

    with session_factory() as db:
        account = db.scalar(select(Account).where(Account.auth_index == "auth-1"))
        assert account is not None
        assert account.current_status_code == 401
        assert account.current_is_401 is True
        assert account.current_invalid_quota is False
        assert account.current_remaining is None

    app.dependency_overrides.clear()


def test_sync_auth_files_generates_transition_events_and_scan_stats() -> None:
    session_factory = _create_session_factory()

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

    auth_files = [
        {
            "name": "Alpha",
            "auth_index": "auth-1",
            "type": "chatgpt",
            "provider": "openai",
            "disabled": False,
            "status": "active",
            "status_message": "ok",
        }
    ]
    fake_client = FakeManagementClient(
        auth_files=auth_files,
        probe_results={
            "auth-1": {
                "status_code": 200,
                "body": {
                    "rate_limit": {
                        "individual_window": {
                            "used_percent": 80,
                            "reset_at": "2026-05-02T00:00:00Z",
                            "limit_window_seconds": 604800,
                        }
                    }
                },
            }
        },
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_management_client] = lambda: fake_client

    first_response = asyncio.run(_request("POST", "/api/v1/sync/auth-files", json={"trigger_mode": "manual"}))
    assert first_response.status_code == 200
    assert first_response.json()["status"] == "success"

    fake_client.probe_results["auth-1"] = {"status_code": 401, "body": {"detail": "unauthorized"}}
    second_response = asyncio.run(_request("POST", "/api/v1/sync/auth-files", json={"trigger_mode": "manual"}))
    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["status"] == "success"

    fake_client.probe_results["auth-1"] = {
        "status_code": 200,
        "body": {
            "rate_limit": {
                "individual_window": {
                    "used_percent": 97,
                    "reset_at": "2026-05-03T00:00:00Z",
                    "limit_window_seconds": 604800,
                }
            }
        },
    }
    third_response = asyncio.run(_request("POST", "/api/v1/sync/auth-files", json={"trigger_mode": "manual"}))
    assert third_response.status_code == 200
    third_payload = third_response.json()
    assert third_payload["status"] == "success"

    with session_factory() as db:
        account = db.scalar(select(Account).where(Account.auth_index == "auth-1"))
        assert account is not None
        scan_jobs = db.scalars(select(ScanJob).order_by(ScanJob.id)).all()
        events = db.scalars(select(AccountEvent).order_by(AccountEvent.id)).all()
        snapshots = db.scalars(
            select(AccountSnapshot).where(AccountSnapshot.account_id == account.id).order_by(AccountSnapshot.id)
        ).all()

        assert len(scan_jobs) == 3
        assert scan_jobs[0].new_401_events == 0
        assert scan_jobs[0].new_quota_events == 0
        assert scan_jobs[1].new_401_events == 1
        assert scan_jobs[1].new_quota_events == 0
        assert scan_jobs[2].new_401_events == 0
        assert scan_jobs[2].new_quota_events == 0
        assert len(snapshots) == 3
        assert len(events) == 2
        assert events[0].event_type == "became_401"
        assert events[0].previous_snapshot_id == snapshots[0].id
        assert events[0].related_snapshot_id == snapshots[1].id
        assert events[1].event_type == "recovered_from_401"
        assert events[1].previous_snapshot_id == snapshots[1].id
        assert events[1].related_snapshot_id == snapshots[2].id
        assert account.current_status_code == 200
        assert account.current_is_401 is False
        assert account.current_invalid_quota is False

    app.dependency_overrides.clear()


def test_partial_failed_probe_does_not_override_current_state_or_emit_recovery_event() -> None:
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
            }
        ],
        probe_results={"auth-1": {"status_code": 500, "body": {"detail": "upstream error"}}},
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
        account = Account(
            source_id=source.id,
            auth_index="auth-1",
            name="Alpha",
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            current_status_code=401,
            current_is_401=True,
            current_invalid_quota=False,
            current_last_checked_at=seen_at,
        )
        db.add(account)
        db.flush()
        scan_job = ScanJob(
            source_id=source.id,
            trigger_mode="manual",
            status="success",
            scan_started_at=seen_at,
            scan_finished_at=seen_at,
        )
        db.add(scan_job)
        db.flush()
        db.add(
            AccountSnapshot(
                account_id=account.id,
                scan_job_id=scan_job.id,
                checked_at=seen_at,
                snapshot_status="success",
                probe_status_code=401,
                is_401=True,
                invalid_quota=False,
                raw_auth_file_json={"disabled": False},
                raw_usage_json={"detail": "unauthorized"},
                created_at=seen_at,
            )
        )
        db.commit()

    response = asyncio.run(_request("POST", "/api/v1/sync/auth-files", json={"trigger_mode": "manual"}))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial_failed"
    assert payload["failed_snapshots"] == 1

    with session_factory() as db:
        account = db.scalar(select(Account).where(Account.auth_index == "auth-1"))
        assert account is not None
        events = db.scalars(select(AccountEvent).where(AccountEvent.account_id == account.id)).all()
        latest_snapshot = db.scalar(
            select(AccountSnapshot)
            .where(AccountSnapshot.account_id == account.id)
            .order_by(AccountSnapshot.id.desc())
        )
        latest_scan_job = db.scalar(select(ScanJob).order_by(ScanJob.id.desc()))

        assert account.current_status_code == 401
        assert account.current_is_401 is True
        assert latest_snapshot is not None
        assert latest_snapshot.snapshot_status == "partial_failed"
        assert latest_scan_job is not None
        assert latest_scan_job.new_401_events == 0
        assert latest_scan_job.new_quota_events == 0
        assert events == []

    app.dependency_overrides.clear()


def test_account_and_event_query_apis_return_timeline_data() -> None:
    session_factory = _create_session_factory()

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
                "email": "alpha@example.com",
            }
        ],
        probe_results={
            "auth-1": {
                "status_code": 200,
                "body": {
                    "rate_limit": {
                        "individual_window": {
                            "used_percent": 70,
                            "reset_at": "2026-05-02T00:00:00Z",
                            "limit_window_seconds": 604800,
                        }
                    }
                },
            }
        },
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_management_client] = lambda: fake_client

    first_response = asyncio.run(_request("POST", "/api/v1/sync/auth-files", json={"trigger_mode": "manual"}))
    assert first_response.status_code == 200

    fake_client.probe_results["auth-1"] = {"status_code": 401, "body": {"detail": "unauthorized"}}
    second_response = asyncio.run(_request("POST", "/api/v1/sync/auth-files", json={"trigger_mode": "manual"}))
    assert second_response.status_code == 200

    accounts_response = asyncio.run(_request("GET", "/api/v1/accounts?current_is_401=true"))
    assert accounts_response.status_code == 200
    accounts_payload = accounts_response.json()
    assert accounts_payload["total"] == 1
    account_payload = accounts_payload["items"][0]
    assert account_payload["auth_index"] == "auth-1"
    assert account_payload["current_status_code"] == 401

    events_response = asyncio.run(_request("GET", "/api/v1/events?event_type=became_401"))
    assert events_response.status_code == 200
    events_payload = events_response.json()
    assert events_payload["total"] == 1
    assert events_payload["limit"] == 50
    assert events_payload["offset"] == 0
    event_payload = events_payload["items"][0]
    assert event_payload["event"]["event_type"] == "became_401"
    assert event_payload["account"]["id"] == account_payload["id"]
    assert event_payload["related_snapshot"]["probe_status_code"] == 401
    assert event_payload["previous_snapshot"]["probe_status_code"] == 200

    event_detail_response = asyncio.run(
        _request("GET", f"/api/v1/events/{event_payload['event']['id']}")
    )
    assert event_detail_response.status_code == 200
    assert event_detail_response.json()["item"]["event"]["event_type"] == "became_401"

    detail_response = asyncio.run(
        _request(
            "GET",
            f"/api/v1/accounts/{account_payload['id']}?snapshot_limit=5&event_limit=5",
        )
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["account"]["id"] == account_payload["id"]
    assert len(detail_payload["recent_snapshots"]) == 2
    assert detail_payload["recent_snapshots"][0]["probe_status_code"] == 401
    assert detail_payload["recent_snapshots"][0]["account_id"] == account_payload["id"]
    assert detail_payload["recent_snapshots"][0]["scan_job_id"] == second_response.json()["scan_job_id"]
    assert detail_payload["recent_snapshots"][0]["raw_usage_json"] == {"detail": "unauthorized"}
    assert detail_payload["recent_snapshots"][1]["raw_usage_json"]["rate_limit"]["individual_window"]["used_percent"] == 70
    assert len(detail_payload["recent_events"]) == 1
    assert detail_payload["recent_events"][0]["event_type"] == "became_401"
    assert detail_payload["provider_cohort"]["total_accounts"] == 1
    assert detail_payload["provider_cohort"]["current_401_accounts"] == 1
    assert detail_payload["account_type_cohort"]["total_accounts"] == 1
    assert detail_payload["provider_account_type_cohort"]["became_401_events_last_24h"] == 1
    assert detail_payload["cohort_usage_position"]["weekly_compared_accounts"] == 0
    assert detail_payload["cohort_usage_position"]["weekly_rank_desc"] is None
    assert detail_payload["risk_overview"]["level"] == "critical"
    assert detail_payload["risk_overview"]["signal_count"] == 3
    assert [signal["key"] for signal in detail_payload["risk_overview"]["signals"]] == [
        "current_401",
        "recent_became_401",
        "peer_group_hot",
    ]
    assert len(detail_payload["provider_account_type_trend"]) == 24
    assert sum(point["snapshot_count"] for point in detail_payload["provider_account_type_trend"]) == 2
    assert sum(point["is_401_count"] for point in detail_payload["provider_account_type_trend"]) == 1

    app.dependency_overrides.clear()


def test_account_detail_returns_cohort_research_summary() -> None:
    session_factory = _create_session_factory()

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

    with session_factory() as db:
        base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        source = ManagementSource(
            source_key=settings.management_source_key,
            source_name=settings.management_source_name,
            base_url=settings.management_base_url or "",
            is_enabled=True,
        )
        db.add(source)
        db.flush()

        alpha = Account(
            source_id=source.id,
            auth_index="auth-1",
            name="Alpha",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_status_code=200,
            current_is_401=False,
            current_invalid_quota=False,
            current_weekly_used_percent=90,
            current_short_used_percent=60,
            current_limit_reached=False,
            current_allowed=True,
            current_last_checked_at=base_time,
            first_seen_at=base_time,
            last_seen_at=base_time,
        )
        beta = Account(
            source_id=source.id,
            auth_index="auth-2",
            name="Beta",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_status_code=401,
            current_is_401=True,
            current_invalid_quota=True,
            current_weekly_used_percent=85,
            current_short_used_percent=20,
            current_limit_reached=True,
            current_allowed=False,
            current_last_checked_at=base_time - timedelta(hours=1),
            first_seen_at=base_time,
            last_seen_at=base_time,
        )
        gamma = Account(
            source_id=source.id,
            auth_index="auth-3",
            name="Gamma",
            provider="openai",
            account_type="chatgpt",
            disabled=True,
            current_status_code=200,
            current_is_401=False,
            current_invalid_quota=False,
            current_weekly_used_percent=40,
            current_last_checked_at=base_time - timedelta(hours=2),
            first_seen_at=base_time,
            last_seen_at=base_time,
        )
        delta = Account(
            source_id=source.id,
            auth_index="auth-4",
            name="Delta",
            provider="openai",
            account_type="claude",
            disabled=False,
            current_status_code=200,
            current_is_401=False,
            current_invalid_quota=False,
            current_weekly_used_percent=95,
            current_short_used_percent=90,
            current_last_checked_at=base_time - timedelta(hours=3),
            first_seen_at=base_time,
            last_seen_at=base_time,
        )
        epsilon = Account(
            source_id=source.id,
            auth_index="auth-5",
            name="Epsilon",
            provider="anthropic",
            account_type="chatgpt",
            disabled=False,
            current_status_code=200,
            current_is_401=False,
            current_invalid_quota=True,
            current_weekly_used_percent=30,
            current_short_used_percent=50,
            current_last_checked_at=base_time - timedelta(hours=4),
            first_seen_at=base_time,
            last_seen_at=base_time,
        )
        zeta = Account(
            source_id=source.id,
            auth_index="auth-6",
            name="Zeta",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_status_code=200,
            current_is_401=False,
            current_invalid_quota=False,
            current_weekly_used_percent=100,
            current_short_used_percent=100,
            current_last_checked_at=base_time - timedelta(hours=5),
            first_seen_at=base_time,
            last_seen_at=base_time,
            source_deleted_at=base_time,
        )
        db.add_all([alpha, beta, gamma, delta, epsilon, zeta])
        db.flush()

        scan_job = ScanJob(
            source_id=source.id,
            trigger_mode="manual",
            status="success",
            scan_started_at=base_time - timedelta(hours=1),
            scan_finished_at=base_time - timedelta(hours=1) + timedelta(minutes=1),
        )
        db.add(scan_job)
        db.flush()

        beta_snapshot = AccountSnapshot(
            account_id=beta.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=1),
            snapshot_status="success",
            probe_status_code=401,
            is_401=True,
            invalid_quota=True,
            raw_auth_file_json={"disabled": False},
            raw_usage_json={"detail": "unauthorized"},
            created_at=base_time - timedelta(hours=1),
        )
        db.add(beta_snapshot)
        db.flush()

        db.add_all(
            [
                AccountEvent(
                    account_id=beta.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(hours=1),
                    related_snapshot_id=beta_snapshot.id,
                    previous_snapshot_id=None,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_invalid_quota=False,
                    to_invalid_quota=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(hours=1),
                ),
                AccountEvent(
                    account_id=beta.id,
                    event_type="quota_exhausted",
                    event_time=base_time - timedelta(minutes=30),
                    related_snapshot_id=beta_snapshot.id,
                    previous_snapshot_id=None,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_invalid_quota=False,
                    to_invalid_quota=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(minutes=30),
                ),
                AccountEvent(
                    account_id=delta.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(days=2),
                    related_snapshot_id=beta_snapshot.id,
                    previous_snapshot_id=None,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_invalid_quota=False,
                    to_invalid_quota=False,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(days=2),
                ),
            ]
        )
        db.commit()

        alpha_id = alpha.id

    response = asyncio.run(_request("GET", f"/api/v1/accounts/{alpha_id}"))
    assert response.status_code == 200
    payload = response.json()

    assert payload["provider_cohort"] == {
        "label": "openai",
        "provider": "openai",
        "account_type": None,
        "total_accounts": 4,
        "active_accounts": 3,
        "disabled_accounts": 1,
        "current_401_accounts": 1,
        "current_invalid_quota_accounts": 0,
        "became_401_events_last_24h": 1,
        "quota_exhausted_events_last_24h": 0,
        "checked_accounts_last_24h": 4,
        "high_weekly_accounts": 0,
        "high_short_accounts": 0,
        "current_limit_reached_accounts": 0,
        "current_blocked_accounts": 0,
        "current_401_rate": 25.0,
        "current_invalid_quota_rate": 0.0,
    }
    assert payload["account_type_cohort"] == {
        "label": "chatgpt",
        "provider": None,
        "account_type": "chatgpt",
        "total_accounts": 4,
        "active_accounts": 3,
        "disabled_accounts": 1,
        "current_401_accounts": 1,
        "current_invalid_quota_accounts": 0,
        "became_401_events_last_24h": 1,
        "quota_exhausted_events_last_24h": 0,
        "checked_accounts_last_24h": 4,
        "high_weekly_accounts": 0,
        "high_short_accounts": 0,
        "current_limit_reached_accounts": 0,
        "current_blocked_accounts": 0,
        "current_401_rate": 25.0,
        "current_invalid_quota_rate": 0.0,
    }
    assert payload["provider_account_type_cohort"] == {
        "label": "openai / chatgpt",
        "provider": "openai",
        "account_type": "chatgpt",
        "total_accounts": 3,
        "active_accounts": 2,
        "disabled_accounts": 1,
        "current_401_accounts": 1,
        "current_invalid_quota_accounts": 0,
        "became_401_events_last_24h": 1,
        "quota_exhausted_events_last_24h": 0,
        "checked_accounts_last_24h": 3,
        "high_weekly_accounts": 0,
        "high_short_accounts": 0,
        "current_limit_reached_accounts": 0,
        "current_blocked_accounts": 0,
        "current_401_rate": 33.33,
        "current_invalid_quota_rate": 0.0,
    }
    assert payload["cohort_usage_position"] == {
        "weekly_compared_accounts": 2,
        "weekly_used_percent": "90.00",
        "weekly_rank_desc": 1,
        "short_compared_accounts": 2,
        "short_used_percent": "60.00",
        "short_rank_desc": 1,
    }
    assert payload["risk_overview"] == {
        "level": "medium",
        "headline": "中风险提示：当前账号存在前置信号，建议继续观察同组变化。",
        "summary": "最近窗口包含 0 条快照，失败 0 次；同组合近 24 小时新增 401 1 次。",
        "signal_count": 1,
        "signals": [
            {
                "key": "peer_group_hot",
                "label": "同组合正在升温",
                "tone": "danger",
                "detail": "同 provider + 类型组合当前 401 率 33.33% ，近 24 小时新增 401 1 次。",
            },
        ],
    }
    assert len(payload["provider_account_type_trend"]) == 24
    assert sum(point["snapshot_count"] for point in payload["provider_account_type_trend"]) == 1
    assert sum(point["is_401_count"] for point in payload["provider_account_type_trend"]) == 1
    assert sum(point["invalid_quota_count"] for point in payload["provider_account_type_trend"]) == 0

    app.dependency_overrides.clear()


def test_dashboard_overview_and_list_filters_support_frontend_queries() -> None:
    session_factory = _create_session_factory()

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

    with session_factory() as db:
        base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        alpha_checked_at = base_time
        beta_checked_at = base_time - timedelta(hours=1)
        delta_checked_at = base_time - timedelta(hours=3)
        gamma_checked_at = base_time - timedelta(days=2)
        first_scan_started_at = base_time - timedelta(hours=2)
        filtered_after = base_time - timedelta(minutes=30)
        filtered_after_text = filtered_after.isoformat().replace("+00:00", "Z")
        source = ManagementSource(
            source_key=settings.management_source_key,
            source_name=settings.management_source_name,
            base_url=settings.management_base_url or "",
            is_enabled=True,
        )
        db.add(source)
        db.flush()

        alpha = Account(
            source_id=source.id,
            auth_index="auth-1",
            name="Alpha",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_status_code=401,
            current_is_401=True,
            current_invalid_quota=False,
            current_last_checked_at=alpha_checked_at,
            first_seen_at=base_time,
            last_seen_at=base_time,
        )
        beta = Account(
            source_id=source.id,
            auth_index="auth-2",
            name="Beta",
            provider="openai",
            account_type="chatgpt",
            disabled=True,
            current_status_code=200,
            current_is_401=False,
            current_invalid_quota=True,
            current_last_checked_at=beta_checked_at,
            first_seen_at=base_time,
            last_seen_at=base_time,
        )
        gamma = Account(
            source_id=source.id,
            auth_index="auth-3",
            name="Gamma",
            provider="anthropic",
            account_type="chatgpt",
            disabled=False,
            current_status_code=200,
            current_is_401=False,
            current_invalid_quota=False,
            current_last_checked_at=gamma_checked_at,
            first_seen_at=base_time,
            last_seen_at=base_time,
            source_deleted_at=base_time,
        )
        delta = Account(
            source_id=source.id,
            auth_index="auth-4",
            name="Delta",
            provider="anthropic",
            account_type="claude",
            disabled=False,
            current_status_code=200,
            current_is_401=False,
            current_invalid_quota=False,
            current_last_checked_at=delta_checked_at,
            first_seen_at=base_time,
            last_seen_at=base_time,
        )
        db.add_all([alpha, beta, gamma, delta])
        db.flush()
        source_id = source.id

        first_scan_job = ScanJob(
            source_id=source.id,
            trigger_mode="manual",
            status="success",
            scan_started_at=first_scan_started_at,
            scan_finished_at=first_scan_started_at + timedelta(minutes=5),
            total_accounts=3,
            eligible_accounts=2,
            scanned_accounts=2,
            success_accounts=2,
            failed_accounts=0,
            new_401_events=1,
            new_quota_events=0,
            duration_ms=300000,
        )
        second_scan_job = ScanJob(
            source_id=source.id,
            trigger_mode="scheduler",
            status="partial_failed",
            scan_started_at=base_time,
            scan_finished_at=base_time + timedelta(minutes=2),
            total_accounts=3,
            eligible_accounts=2,
            scanned_accounts=2,
            success_accounts=1,
            failed_accounts=1,
            new_401_events=0,
            new_quota_events=1,
            duration_ms=120000,
        )
        db.add_all([first_scan_job, second_scan_job])
        db.flush()

        previous_snapshot = AccountSnapshot(
            account_id=alpha.id,
            scan_job_id=first_scan_job.id,
            checked_at=first_scan_started_at,
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            invalid_quota=False,
            raw_auth_file_json={"disabled": False},
            raw_usage_json={"detail": "ok"},
            created_at=first_scan_started_at,
        )
        current_snapshot = AccountSnapshot(
            account_id=alpha.id,
            scan_job_id=second_scan_job.id,
            checked_at=alpha_checked_at,
            snapshot_status="success",
            probe_status_code=401,
            is_401=True,
            invalid_quota=False,
            raw_auth_file_json={"disabled": False},
            raw_usage_json={"detail": "unauthorized"},
            created_at=alpha_checked_at,
        )
        quota_snapshot = AccountSnapshot(
            account_id=beta.id,
            scan_job_id=second_scan_job.id,
            checked_at=beta_checked_at,
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            invalid_quota=True,
            raw_auth_file_json={"disabled": True},
            raw_usage_json={"detail": "quota"},
            created_at=beta_checked_at,
        )
        db.add_all([previous_snapshot, current_snapshot, quota_snapshot])
        db.flush()

        db.add_all(
            [
                AccountEvent(
                    account_id=alpha.id,
                    event_type="became_401",
                    event_time=alpha_checked_at,
                    related_snapshot_id=current_snapshot.id,
                    previous_snapshot_id=previous_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_invalid_quota=False,
                    to_invalid_quota=False,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=alpha_checked_at,
                ),
                AccountEvent(
                    account_id=beta.id,
                    event_type="quota_exhausted",
                    event_time=beta_checked_at,
                    related_snapshot_id=quota_snapshot.id,
                    previous_snapshot_id=None,
                    from_status_code=200,
                    to_status_code=200,
                    from_is_401=False,
                    to_is_401=False,
                    from_invalid_quota=False,
                    to_invalid_quota=True,
                    from_disabled=True,
                    to_disabled=True,
                    created_at=beta_checked_at,
                ),
            ]
        )
        db.commit()

    overview_response = asyncio.run(_request("GET", "/api/v1/dashboard/overview"))
    assert overview_response.status_code == 200
    overview_payload = overview_response.json()
    assert overview_payload["total_accounts"] == 4
    assert overview_payload["active_accounts"] == 2
    assert overview_payload["disabled_accounts"] == 1
    assert overview_payload["deleted_accounts"] == 1
    assert overview_payload["current_401_accounts"] == 1
    assert overview_payload["current_invalid_quota_accounts"] == 1
    assert overview_payload["new_401_events_last_24h"] == 1
    assert overview_payload["new_quota_events_last_24h"] == 1
    assert len(overview_payload["recent_401_trend"]) == 24
    assert overview_payload["latest_scan_job"]["source_id"] == source_id
    assert overview_payload["latest_scan_job"]["trigger_mode"] == "scheduler"
    assert overview_payload["latest_scan_job"]["error_message"] is None
    assert overview_payload["provider_breakdown"] == [
        {
            "value": "openai",
            "label": "openai",
            "total_accounts": 2,
            "active_accounts": 1,
            "disabled_accounts": 1,
            "current_401_accounts": 1,
            "current_invalid_quota_accounts": 1,
            "became_401_events_last_24h": 1,
            "current_401_rate": 50.0,
            "current_invalid_quota_rate": 50.0,
        },
        {
            "value": "anthropic",
            "label": "anthropic",
            "total_accounts": 1,
            "active_accounts": 1,
            "disabled_accounts": 0,
            "current_401_accounts": 0,
            "current_invalid_quota_accounts": 0,
            "became_401_events_last_24h": 0,
            "current_401_rate": 0.0,
            "current_invalid_quota_rate": 0.0,
        },
    ]
    assert overview_payload["account_type_breakdown"] == [
        {
            "value": "chatgpt",
            "label": "chatgpt",
            "total_accounts": 2,
            "active_accounts": 1,
            "disabled_accounts": 1,
            "current_401_accounts": 1,
            "current_invalid_quota_accounts": 1,
            "became_401_events_last_24h": 1,
            "current_401_rate": 50.0,
            "current_invalid_quota_rate": 50.0,
        },
        {
            "value": "claude",
            "label": "claude",
            "total_accounts": 1,
            "active_accounts": 1,
            "disabled_accounts": 0,
            "current_401_accounts": 0,
            "current_invalid_quota_accounts": 0,
            "became_401_events_last_24h": 0,
            "current_401_rate": 0.0,
            "current_invalid_quota_rate": 0.0,
        },
    ]

    accounts_response = asyncio.run(
        _request(
            "GET",
            f"/api/v1/accounts?include_deleted=true&last_checked_from={filtered_after_text}&limit=1&offset=0",
        )
    )
    assert accounts_response.status_code == 200
    accounts_payload = accounts_response.json()
    assert accounts_payload["total"] == 1
    assert accounts_payload["limit"] == 1
    assert accounts_payload["offset"] == 0
    assert len(accounts_payload["items"]) == 1
    assert accounts_payload["items"][0]["auth_index"] == "auth-1"

    events_response = asyncio.run(
        _request(
            "GET",
            f"/api/v1/events?event_time_from={filtered_after_text}&limit=1&offset=0",
        )
    )
    assert events_response.status_code == 200
    events_payload = events_response.json()
    assert events_payload["total"] == 1
    assert events_payload["limit"] == 1
    assert events_payload["offset"] == 0
    assert events_payload["items"][0]["event"]["event_type"] == "became_401"

    missing_event_response = asyncio.run(_request("GET", "/api/v1/events/999"))
    assert missing_event_response.status_code == 404

    app.dependency_overrides.clear()


def test_dashboard_overview_normalizes_blank_latest_scan_job_error_message() -> None:
    session_factory = _create_session_factory()

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
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings

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
                status="failed",
                scan_started_at=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
                scan_finished_at=datetime(2026, 5, 2, 12, 1, tzinfo=timezone.utc),
                total_accounts=3,
                eligible_accounts=3,
                scanned_accounts=3,
                success_accounts=0,
                failed_accounts=3,
                new_401_events=0,
                new_quota_events=0,
                duration_ms=60000,
                error_message=" ",
            )
        )
        db.commit()

    response = asyncio.run(_request("GET", "/api/v1/dashboard/overview"))
    assert response.status_code == 200
    assert response.json()["latest_scan_job"]["error_message"] == LEGACY_BLANK_ERROR_MESSAGE

    app.dependency_overrides.clear()


def test_scan_job_query_apis_return_paginated_runs_and_error_details() -> None:
    session_factory = _create_session_factory()

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

    with session_factory() as db:
        base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        source = ManagementSource(
            source_key=settings.management_source_key,
            source_name=settings.management_source_name,
            base_url=settings.management_base_url or "",
            is_enabled=True,
        )
        db.add(source)
        db.flush()
        source_id = source.id
        db.add_all(
            [
                ScanJob(
                    source_id=source.id,
                    trigger_mode="manual",
                    status="success",
                    scan_started_at=base_time - timedelta(hours=2),
                    scan_finished_at=base_time - timedelta(hours=2) + timedelta(minutes=4),
                    total_accounts=10,
                    eligible_accounts=8,
                    scanned_accounts=8,
                    success_accounts=8,
                    failed_accounts=0,
                    new_401_events=1,
                    new_quota_events=0,
                    duration_ms=240000,
                ),
                ScanJob(
                    source_id=source.id,
                    trigger_mode="scheduler",
                    status="partial_failed",
                    scan_started_at=base_time - timedelta(hours=1),
                    scan_finished_at=base_time - timedelta(hours=1) + timedelta(minutes=3),
                    total_accounts=10,
                    eligible_accounts=8,
                    scanned_accounts=8,
                    success_accounts=6,
                    failed_accounts=2,
                    new_401_events=0,
                    new_quota_events=1,
                    duration_ms=180000,
                    error_message="probe timeout on auth-2",
                ),
                ScanJob(
                    source_id=source.id,
                    trigger_mode="scheduler",
                    status="running",
                    scan_started_at=base_time,
                    scan_finished_at=None,
                    total_accounts=12,
                    eligible_accounts=10,
                    scanned_accounts=4,
                    success_accounts=4,
                    failed_accounts=0,
                    new_401_events=0,
                    new_quota_events=0,
                    duration_ms=None,
                ),
            ]
        )
        db.commit()

    list_response = asyncio.run(
        _request(
            "GET",
            "/api/v1/scan-jobs?status=partial_failed&trigger_mode=scheduler&limit=1&offset=0",
        )
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["limit"] == 1
    assert list_payload["offset"] == 0
    assert len(list_payload["items"]) == 1
    assert list_payload["items"][0]["id"] == 2
    assert list_payload["items"][0]["source_id"] == source_id
    assert list_payload["items"][0]["trigger_mode"] == "scheduler"
    assert list_payload["items"][0]["status"] == "partial_failed"
    assert list_payload["items"][0]["scan_started_at"].startswith(
        (base_time - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    )
    assert list_payload["items"][0]["scan_finished_at"].startswith(
        (base_time - timedelta(hours=1) + timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%S")
    )
    assert list_payload["items"][0]["total_accounts"] == 10
    assert list_payload["items"][0]["eligible_accounts"] == 8
    assert list_payload["items"][0]["scanned_accounts"] == 8
    assert list_payload["items"][0]["success_accounts"] == 6
    assert list_payload["items"][0]["failed_accounts"] == 2
    assert list_payload["items"][0]["new_401_events"] == 0
    assert list_payload["items"][0]["new_quota_events"] == 1
    assert list_payload["items"][0]["duration_ms"] == 180000
    assert list_payload["items"][0]["error_message"] == "probe timeout on auth-2"

    detail_response = asyncio.run(_request("GET", "/api/v1/scan-jobs/3"))
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["item"]["status"] == "running"
    assert detail_payload["item"]["scan_finished_at"] is None
    assert detail_payload["item"]["error_message"] is None
    assert detail_payload["snapshot_stats"] == {
        "total_snapshots": 0,
        "success_snapshots": 0,
        "partial_failed_snapshots": 0,
        "failed_snapshots": 0,
        "is_401_snapshots": 0,
        "invalid_quota_snapshots": 0,
    }
    assert detail_payload["diagnostic_summary"] == {
        "abnormal_probe_status_samples": 0,
        "abnormal_probe_status_breakdown": [],
        "top_failure_reasons": [],
    }
    assert detail_payload["recent_failure_samples"] == []
    assert detail_payload["recent_401_samples"] == []
    assert detail_payload["recent_quota_samples"] == []

    missing_response = asyncio.run(_request("GET", "/api/v1/scan-jobs/999"))
    assert missing_response.status_code == 404

    app.dependency_overrides.clear()


def test_scan_job_api_normalizes_blank_legacy_error_messages() -> None:
    session_factory = _create_session_factory()

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
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings

    with session_factory() as db:
        source = ManagementSource(
            source_key=settings.management_source_key,
            source_name=settings.management_source_name,
            base_url=settings.management_base_url or "",
            is_enabled=True,
        )
        db.add(source)
        db.flush()

        account = Account(
            source_id=source.id,
            auth_index="auth-legacy",
            name="legacy.json",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_invalid_quota=False,
            first_seen_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
            last_seen_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
        )
        db.add(account)
        db.flush()

        scan_job = ScanJob(
            source_id=source.id,
            trigger_mode="manual",
            status="failed",
            scan_started_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
            scan_finished_at=datetime(2026, 5, 2, 10, 1, tzinfo=timezone.utc),
            total_accounts=1,
            eligible_accounts=1,
            scanned_accounts=1,
            success_accounts=0,
            failed_accounts=1,
            new_401_events=0,
            new_quota_events=0,
            duration_ms=60000,
            error_message="   ",
        )
        db.add(scan_job)
        db.flush()
        scan_job_id = scan_job.id

        db.add(
            AccountSnapshot(
                account_id=account.id,
                scan_job_id=scan_job_id,
                checked_at=datetime(2026, 5, 2, 10, 0, 30, tzinfo=timezone.utc),
                created_at=datetime(2026, 5, 2, 10, 0, 30, tzinfo=timezone.utc),
                snapshot_status="failed",
                probe_status_code=None,
                is_401=False,
                invalid_quota=False,
                raw_auth_file_json={"disabled": False},
                error_message="   ",
            )
        )
        db.commit()

    list_response = asyncio.run(_request("GET", "/api/v1/scan-jobs?limit=5"))
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["error_message"] == LEGACY_BLANK_ERROR_MESSAGE

    detail_response = asyncio.run(_request("GET", f"/api/v1/scan-jobs/{scan_job_id}"))
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["item"]["error_message"] == LEGACY_BLANK_ERROR_MESSAGE
    assert detail_payload["recent_failure_samples"][0]["error_message"] == LEGACY_BLANK_ERROR_MESSAGE

    app.dependency_overrides.clear()


def test_event_detail_api_returns_event_context_snapshots_and_events() -> None:
    session_factory = _create_session_factory()

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
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings

    with session_factory() as db:
        base_time = datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc)
        source = ManagementSource(
            source_key=settings.management_source_key,
            source_name=settings.management_source_name,
            base_url=settings.management_base_url or "",
            is_enabled=True,
        )
        db.add(source)
        db.flush()

        account = Account(
            source_id=source.id,
            auth_index="auth-1",
            name="Alpha",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_status_code=200,
            current_is_401=False,
            current_last_checked_at=base_time + timedelta(minutes=10),
            first_seen_at=base_time,
            last_seen_at=base_time + timedelta(minutes=10),
        )
        db.add(account)
        db.flush()

        first_scan_job = ScanJob(
            source_id=source.id,
            trigger_mode="manual",
            status="success",
            scan_started_at=base_time,
            scan_finished_at=base_time + timedelta(minutes=1),
        )
        second_scan_job = ScanJob(
            source_id=source.id,
            trigger_mode="manual",
            status="success",
            scan_started_at=base_time + timedelta(minutes=4),
            scan_finished_at=base_time + timedelta(minutes=5),
        )
        third_scan_job = ScanJob(
            source_id=source.id,
            trigger_mode="scheduler",
            status="success",
            scan_started_at=base_time + timedelta(minutes=9),
            scan_finished_at=base_time + timedelta(minutes=10),
        )
        db.add_all([first_scan_job, second_scan_job, third_scan_job])
        db.flush()

        healthy_snapshot = AccountSnapshot(
            account_id=account.id,
            scan_job_id=first_scan_job.id,
            checked_at=base_time + timedelta(minutes=1),
            created_at=base_time + timedelta(minutes=1),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("72.00"),
            raw_auth_file_json={"disabled": False},
            raw_usage_json={"detail": "healthy"},
        )
        became_401_snapshot = AccountSnapshot(
            account_id=account.id,
            scan_job_id=second_scan_job.id,
            checked_at=base_time + timedelta(minutes=5),
            created_at=base_time + timedelta(minutes=5),
            snapshot_status="success",
            probe_status_code=401,
            is_401=True,
            raw_auth_file_json={"disabled": False},
            raw_usage_json={"detail": "unauthorized"},
        )
        recovered_snapshot = AccountSnapshot(
            account_id=account.id,
            scan_job_id=third_scan_job.id,
            checked_at=base_time + timedelta(minutes=10),
            created_at=base_time + timedelta(minutes=10),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("41.00"),
            raw_auth_file_json={"disabled": False},
            raw_usage_json={"detail": "recovered"},
        )
        db.add_all([healthy_snapshot, became_401_snapshot, recovered_snapshot])
        db.flush()

        became_401_event = AccountEvent(
            account_id=account.id,
            event_type="became_401",
            event_time=became_401_snapshot.checked_at,
            related_snapshot_id=became_401_snapshot.id,
            previous_snapshot_id=healthy_snapshot.id,
            from_status_code=200,
            to_status_code=401,
            from_is_401=False,
            to_is_401=True,
            from_disabled=False,
            to_disabled=False,
            created_at=became_401_snapshot.checked_at,
        )
        recovered_event = AccountEvent(
            account_id=account.id,
            event_type="recovered_from_401",
            event_time=recovered_snapshot.checked_at,
            related_snapshot_id=recovered_snapshot.id,
            previous_snapshot_id=became_401_snapshot.id,
            from_status_code=401,
            to_status_code=200,
            from_is_401=True,
            to_is_401=False,
            from_disabled=False,
            to_disabled=False,
            created_at=recovered_snapshot.checked_at,
        )
        db.add_all([became_401_event, recovered_event])
        db.commit()
        became_401_event_id = became_401_event.id
        first_scan_job_id = first_scan_job.id
        second_scan_job_id = second_scan_job.id

    response = asyncio.run(
        _request(
            "GET",
            f"/api/v1/events/{became_401_event_id}?snapshot_limit=3&event_limit=3",
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["item"]["event"]["event_type"] == "became_401"
    assert payload["item"]["related_snapshot"]["raw_usage_json"] == {"detail": "unauthorized"}
    assert payload["item"]["previous_snapshot"]["raw_usage_json"] == {"detail": "healthy"}
    assert [snapshot["probe_status_code"] for snapshot in payload["context_snapshots"]] == [401, 200]
    assert payload["context_snapshots"][0]["scan_job_id"] == second_scan_job_id
    assert payload["context_snapshots"][1]["scan_job_id"] == first_scan_job_id
    assert [event["event_type"] for event in payload["context_events"]] == ["became_401"]

    app.dependency_overrides.clear()


def test_scan_job_detail_api_returns_failure_and_risk_samples() -> None:
    session_factory = _create_session_factory()

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
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_app_settings] = lambda: settings

    with session_factory() as db:
        seen_at = datetime(2026, 5, 2, 9, 55, tzinfo=timezone.utc)
        source = ManagementSource(
            source_key=settings.management_source_key,
            source_name=settings.management_source_name,
            base_url=settings.management_base_url or "",
            is_enabled=True,
        )
        db.add(source)
        db.flush()

        scan_job = ScanJob(
            source_id=source.id,
            trigger_mode="scheduler",
            status="partial_failed",
            scan_started_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
            scan_finished_at=datetime(2026, 5, 2, 10, 4, tzinfo=timezone.utc),
            total_accounts=4,
            eligible_accounts=4,
            scanned_accounts=4,
            success_accounts=2,
            failed_accounts=2,
            new_401_events=1,
            new_quota_events=1,
            duration_ms=240000,
            error_message="2 probes failed",
        )
        db.add(scan_job)
        db.flush()
        scan_job_id = scan_job.id

        account_ok = Account(
            source_id=source.id,
            auth_index="auth-ok",
            name="账号-正常",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        account_401 = Account(
            source_id=source.id,
            auth_index="auth-401",
            name="账号-401",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        account_quota = Account(
            source_id=source.id,
            auth_index="auth-quota",
            name="账号-额度",
            provider="azure",
            account_type="chatgpt",
            disabled=False,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        account_failed = Account(
            source_id=source.id,
            auth_index="auth-failed",
            name="账号-失败",
            provider="azure",
            account_type="api",
            disabled=True,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        db.add_all([account_ok, account_401, account_quota, account_failed])
        db.flush()

        db.add_all(
                [
                    AccountSnapshot(
                        account_id=account_ok.id,
                        scan_job_id=scan_job.id,
                        checked_at=datetime(2026, 5, 2, 10, 1, tzinfo=timezone.utc),
                        created_at=datetime(2026, 5, 2, 10, 1, tzinfo=timezone.utc),
                        snapshot_status="success",
                        probe_status_code=200,
                        is_401=False,
                        invalid_quota=False,
                        remaining=Decimal("21.50"),
                        raw_auth_file_json={"disabled": False, "provider": "openai"},
                        raw_usage_json={"detail": "healthy"},
                ),
                    AccountSnapshot(
                        account_id=account_401.id,
                        scan_job_id=scan_job.id,
                        checked_at=datetime(2026, 5, 2, 10, 2, tzinfo=timezone.utc),
                        created_at=datetime(2026, 5, 2, 10, 2, tzinfo=timezone.utc),
                        snapshot_status="success",
                        probe_status_code=401,
                        is_401=True,
                        invalid_quota=False,
                        raw_auth_file_json={"disabled": False, "provider": "openai"},
                        raw_usage_json={"detail": "unauthorized"},
                        error_message=None,
                ),
                    AccountSnapshot(
                        account_id=account_quota.id,
                        scan_job_id=scan_job.id,
                        checked_at=datetime(2026, 5, 2, 10, 3, tzinfo=timezone.utc),
                        created_at=datetime(2026, 5, 2, 10, 3, tzinfo=timezone.utc),
                        snapshot_status="partial_failed",
                        probe_status_code=200,
                        is_401=False,
                        invalid_quota=True,
                        weekly_used_percent=Decimal("96.00"),
                        remaining=Decimal("0"),
                        raw_auth_file_json={"disabled": False, "provider": "azure"},
                        raw_usage_json={"detail": "quota", "remaining": 0},
                        error_message="usage body 不是有效 JSON 对象",
                        status_message="quota_exceeded",
                ),
                    AccountSnapshot(
                        account_id=account_failed.id,
                        scan_job_id=scan_job.id,
                        checked_at=datetime(2026, 5, 2, 10, 4, tzinfo=timezone.utc),
                        created_at=datetime(2026, 5, 2, 10, 4, tzinfo=timezone.utc),
                        snapshot_status="failed",
                        probe_status_code=None,
                        is_401=False,
                        invalid_quota=False,
                        raw_auth_file_json={"disabled": True, "provider": "azure"},
                        error_message="probe timeout",
                ),
            ]
        )
        db.commit()

    response = asyncio.run(_request("GET", f"/api/v1/scan-jobs/{scan_job_id}"))
    assert response.status_code == 200
    payload = response.json()

    assert payload["item"]["id"] == scan_job_id
    assert payload["snapshot_stats"] == {
        "total_snapshots": 4,
        "success_snapshots": 2,
        "partial_failed_snapshots": 1,
        "failed_snapshots": 1,
        "is_401_snapshots": 1,
        "invalid_quota_snapshots": 1,
    }
    assert payload["diagnostic_summary"] == {
        "abnormal_probe_status_samples": 2,
        "abnormal_probe_status_breakdown": [
            {"key": "401", "label": "HTTP 401", "count": 1},
            {"key": "none", "label": "未返回状态码", "count": 1},
        ],
        "top_failure_reasons": [
            {"key": "probe timeout", "label": "probe timeout", "count": 1},
            {"key": "usage body 不是有效 JSON 对象", "label": "usage body 不是有效 JSON 对象", "count": 1},
        ],
    }

    assert [item["account"]["auth_index"] for item in payload["recent_failure_samples"]] == [
        "auth-failed",
        "auth-quota",
    ]
    assert payload["recent_failure_samples"][0]["error_message"] == "probe timeout"
    assert payload["recent_failure_samples"][0]["account"]["disabled"] is True
    assert payload["recent_failure_samples"][0]["raw_auth_file_json"] == {"disabled": True, "provider": "azure"}
    assert payload["recent_failure_samples"][1]["raw_usage_json"] == {"detail": "quota", "remaining": 0}

    assert [item["account"]["auth_index"] for item in payload["recent_401_samples"]] == ["auth-401"]
    assert payload["recent_401_samples"][0]["probe_status_code"] == 401
    assert payload["recent_401_samples"][0]["raw_usage_json"] == {"detail": "unauthorized"}

    assert [item["account"]["auth_index"] for item in payload["recent_quota_samples"]] == ["auth-quota"]
    assert payload["recent_quota_samples"][0]["weekly_used_percent"] == "96.00"
    assert payload["recent_quota_samples"][0]["status_message"] == "quota_exceeded"
    assert payload["recent_quota_samples"][0]["account_id"] == 3

    app.dependency_overrides.clear()
