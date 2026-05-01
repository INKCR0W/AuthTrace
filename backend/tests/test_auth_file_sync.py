from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_app_settings, get_db_session, get_management_client
from app.core.config import Settings
from app.main import app
from app.models.account import Account
from app.models.account_event import AccountEvent
from app.models.account_snapshot import AccountSnapshot
from app.models.management_source import ManagementSource
from app.models.scan_job import ScanJob


class FakeManagementClient:
    def __init__(
        self,
        auth_files: list[dict[str, object]],
        probe_results: dict[str, dict[str, object]] | None = None,
        probe_errors: dict[str, Exception] | None = None,
    ) -> None:
        self.auth_files = auth_files
        self.probe_results = probe_results or {}
        self.probe_errors = probe_errors or {}
        self.refresh_called = False
        self.probe_calls: list[tuple[str, str | None]] = []

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
        self.probe_calls.append((auth_index, chatgpt_account_id))
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
        assert scan_jobs[2].new_quota_events == 1
        assert len(snapshots) == 3
        assert len(events) == 3
        assert events[0].event_type == "became_401"
        assert events[0].previous_snapshot_id == snapshots[0].id
        assert events[0].related_snapshot_id == snapshots[1].id
        assert events[1].event_type == "recovered_from_401"
        assert events[1].previous_snapshot_id == snapshots[1].id
        assert events[1].related_snapshot_id == snapshots[2].id
        assert events[2].event_type == "quota_exhausted"
        assert account.current_status_code == 200
        assert account.current_is_401 is False
        assert account.current_invalid_quota is True

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
    assert len(detail_payload["recent_events"]) == 1
    assert detail_payload["recent_events"][0]["event_type"] == "became_401"

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
        db.add_all([alpha, beta, gamma])
        db.flush()

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
    assert overview_payload["total_accounts"] == 3
    assert overview_payload["active_accounts"] == 1
    assert overview_payload["disabled_accounts"] == 1
    assert overview_payload["deleted_accounts"] == 1
    assert overview_payload["current_401_accounts"] == 1
    assert overview_payload["current_invalid_quota_accounts"] == 1
    assert overview_payload["new_401_events_last_24h"] == 1
    assert overview_payload["new_quota_events_last_24h"] == 1
    assert len(overview_payload["recent_401_trend"]) == 24
    assert overview_payload["latest_scan_job"]["trigger_mode"] == "scheduler"

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
