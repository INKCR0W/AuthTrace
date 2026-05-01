from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import create_engine
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
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path)


def test_research_overview_api_returns_distribution_and_pre_401_insights() -> None:
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
        base_time = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
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
            status="success",
            scan_started_at=base_time - timedelta(hours=3),
            scan_finished_at=base_time - timedelta(hours=3) + timedelta(minutes=3),
            total_accounts=4,
            eligible_accounts=4,
            scanned_accounts=4,
            success_accounts=4,
            failed_accounts=0,
            new_401_events=2,
        )
        db.add(scan_job)
        db.flush()

        openai_hot = Account(
            source_id=source.id,
            auth_index="auth-openai-hot",
            name="OpenAI-Hot",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=10),
            last_seen_at=base_time,
        )
        openai_ok = Account(
            source_id=source.id,
            auth_index="auth-openai-ok",
            name="OpenAI-OK",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=10),
            last_seen_at=base_time,
        )
        azure_hot = Account(
            source_id=source.id,
            auth_index="auth-azure-hot",
            name="Azure-Hot",
            provider="azure",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=10),
            last_seen_at=base_time,
        )
        openai_disabled = Account(
            source_id=source.id,
            auth_index="auth-openai-disabled",
            name="OpenAI-Disabled",
            provider="openai",
            account_type="api",
            disabled=True,
            current_is_401=False,
            current_status_code=200,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=10),
            last_seen_at=base_time,
        )
        db.add_all([openai_hot, openai_ok, azure_hot, openai_disabled])
        db.flush()

        prev_openai_hot = AccountSnapshot(
            account_id=openai_hot.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=1, minutes=5),
            created_at=base_time - timedelta(hours=1, minutes=5),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("95.00"),
            short_used_percent=Decimal("88.00"),
            remaining=Decimal("4.00"),
            limit_reached=True,
            allowed=False,
            status_message="soft_block",
        )
        prev_azure_hot = AccountSnapshot(
            account_id=azure_hot.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=2, minutes=5),
            created_at=base_time - timedelta(hours=2, minutes=5),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("52.00"),
            short_used_percent=Decimal("91.00"),
            remaining=Decimal("0.00"),
            limit_reached=False,
            allowed=True,
            status_message=None,
        )
        prev_openai_old = AccountSnapshot(
            account_id=openai_hot.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(days=3, minutes=10),
            created_at=base_time - timedelta(days=3, minutes=10),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=None,
            short_used_percent=None,
            remaining=Decimal("12.00"),
            limit_reached=False,
            allowed=True,
            status_message="warmup",
        )
        db.add_all([prev_openai_hot, prev_azure_hot, prev_openai_old])
        db.flush()

        db.add_all(
            [
                AccountEvent(
                    account_id=openai_hot.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(hours=1),
                    related_snapshot_id=prev_openai_hot.id,
                    previous_snapshot_id=prev_openai_hot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(hours=1),
                ),
                AccountEvent(
                    account_id=azure_hot.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(hours=2),
                    related_snapshot_id=prev_azure_hot.id,
                    previous_snapshot_id=prev_azure_hot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(hours=2),
                ),
                AccountEvent(
                    account_id=openai_hot.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(days=3),
                    related_snapshot_id=prev_openai_old.id,
                    previous_snapshot_id=prev_openai_old.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(days=3),
                ),
                AccountEvent(
                    account_id=openai_disabled.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(days=9),
                    related_snapshot_id=prev_openai_old.id,
                    previous_snapshot_id=prev_openai_old.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=True,
                    to_disabled=True,
                    created_at=base_time - timedelta(days=9),
                ),
            ]
        )
        db.commit()

    response = asyncio.run(_request("GET", "/api/v1/research/overview?window_days=7"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["window_days"] == 7
    assert payload["summary"] == {
        "active_accounts": 3,
        "current_401_accounts": 2,
        "current_401_rate": 50.0,
        "became_401_events": 3,
        "affected_accounts": 2,
        "affected_provider_groups": 2,
        "sampled_previous_snapshots": 3,
    }

    breakdown = payload["provider_account_type_breakdown"]
    assert [item["label"] for item in breakdown[:3]] == [
        "openai / chatgpt",
        "azure / chatgpt",
        "openai / api",
    ]
    assert breakdown[0]["became_401_events"] == 2
    assert breakdown[0]["affected_accounts"] == 1
    assert breakdown[0]["current_401_rate"] == 50.0
    assert breakdown[1]["became_401_events"] == 1
    assert breakdown[1]["current_401_rate"] == 100.0
    assert breakdown[2]["became_401_events"] == 0

    hour_map = {
        item["hour_of_day"]: item["became_401_count"]
        for item in payload["event_hour_distribution"]
    }
    assert hour_map[10] == 1
    assert hour_map[11] == 1
    assert hour_map[12] == 1
    assert hour_map[9] == 0

    insights = payload["pre_401_insights"]
    assert insights["sampled_events"] == 3
    assert insights["events_with_previous_snapshot"] == 3
    assert insights["weekly_used_percent_bands"] == [
        {"key": "0_24", "label": "0-24%", "count": 0},
        {"key": "25_49", "label": "25-49%", "count": 0},
        {"key": "50_74", "label": "50-74%", "count": 1},
        {"key": "75_89", "label": "75-89%", "count": 0},
        {"key": "90_100", "label": "90-100%", "count": 1},
        {"key": "missing", "label": "未记录", "count": 1},
    ]
    assert insights["short_used_percent_bands"] == [
        {"key": "0_24", "label": "0-24%", "count": 0},
        {"key": "25_49", "label": "25-49%", "count": 0},
        {"key": "50_74", "label": "50-74%", "count": 0},
        {"key": "75_89", "label": "75-89%", "count": 1},
        {"key": "90_100", "label": "90-100%", "count": 1},
        {"key": "missing", "label": "未记录", "count": 1},
    ]
    signal_map = {item["key"]: item["count"] for item in insights["signal_breakdown"]}
    assert signal_map == {
        "status_message_present": 2,
        "allowed_false": 1,
        "limit_reached": 1,
        "remaining_empty": 1,
        "short_ge_90": 1,
        "weekly_ge_90": 1,
    }
    assert insights["top_status_messages"] == [
        {"key": "soft_block", "label": "soft_block", "count": 1},
        {"key": "warmup", "label": "warmup", "count": 1},
    ]

    app.dependency_overrides.clear()
