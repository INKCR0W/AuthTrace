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
            status_message='{"error":{"type":"usage_limit_reached","message":"The usage limit has been reached"}}',
        )
        prev_azure_hot = AccountSnapshot(
            account_id=azure_hot.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=4, minutes=30),
            created_at=base_time - timedelta(hours=4, minutes=30),
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
            checked_at=base_time - timedelta(days=4, hours=6),
            created_at=base_time - timedelta(days=4, hours=6),
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
    assert insights["previous_to_event_gap_bands"] == [
        {"key": "lt_15m", "label": "15 分钟内", "count": 1},
        {"key": "15m_1h", "label": "15-60 分钟", "count": 0},
        {"key": "1h_6h", "label": "1-6 小时", "count": 1},
        {"key": "6h_24h", "label": "6-24 小时", "count": 0},
        {"key": "24h_plus", "label": "24 小时以上", "count": 1},
    ]
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
    assert {item["key"]: item["count"] for item in insights["signal_pattern_breakdown"]} == {
        "status_message_present": 1,
        "short_ge_90|remaining_empty": 1,
        "weekly_ge_90|limit_reached|allowed_false|status_message_present": 1,
    }
    assert insights["top_status_messages"] == [
        {
            "key": "usage_limit_reached: The usage limit has been reached",
            "label": "usage_limit_reached: The usage limit has been reached",
            "count": 1,
        },
        {"key": "warmup", "label": "warmup", "count": 1},
    ]
    signal_comparison = {
        item["key"]: (
            item["pre_401_count"],
            item["pre_401_rate"],
            item["current_count"],
            item["current_rate"],
            item["rate_gap"],
        )
        for item in payload["signal_comparison"]
    }
    assert len(payload["signal_comparison"]) == 6
    assert payload["signal_comparison"][0]["key"] == "status_message_present"
    assert signal_comparison == {
        "weekly_ge_90": (1, 33.33, 0, 0.0, 33.33),
        "short_ge_90": (1, 33.33, 0, 0.0, 33.33),
        "limit_reached": (1, 33.33, 0, 0.0, 33.33),
        "allowed_false": (1, 33.33, 0, 0.0, 33.33),
        "remaining_empty": (1, 33.33, 0, 0.0, 33.33),
        "status_message_present": (2, 66.67, 0, 0.0, 66.67),
    }
    signal_pattern_comparison = {
        item["key"]: (
            item["pre_401_count"],
            item["pre_401_rate"],
            item["current_count"],
            item["current_rate"],
            item["rate_gap"],
        )
        for item in payload["signal_pattern_comparison"]
    }
    assert signal_pattern_comparison == {
        "weekly_ge_90|limit_reached|allowed_false|status_message_present": (1, 33.33, 0, 0.0, 33.33),
        "short_ge_90|remaining_empty": (1, 33.33, 0, 0.0, 33.33),
        "status_message_present": (1, 33.33, 0, 0.0, 33.33),
    }

    recent_samples = payload["recent_event_samples"]
    assert [item["event_id"] for item in recent_samples[:3]] == [1, 2, 3]
    assert recent_samples[0] == {
        "event_id": 1,
        "account_id": 1,
        "account_name": "OpenAI-Hot",
        "provider": "openai",
        "account_type": "chatgpt",
        "event_time": "2026-05-02T11:00:00Z",
        "current_is_401": True,
        "previous_snapshot_id": 1,
        "previous_checked_at": "2026-05-02T10:55:00Z",
        "previous_to_event_gap_minutes": 5,
        "previous_weekly_used_percent": "95.00",
        "previous_short_used_percent": "88.00",
        "previous_remaining": "4.00",
        "previous_limit_reached": True,
        "previous_allowed": False,
        "previous_status_message": "usage_limit_reached: The usage limit has been reached",
    }
    assert recent_samples[2]["previous_status_message"] == "warmup"
    assert payload["current_signal_baseline"] == {
        "observed_accounts": 1,
        "signal_accounts": 0,
        "signal_breakdown": [],
        "signal_pattern_breakdown": [],
        "signal_streak_breakdown": [],
        "historical_match_breakdown": [],
        "historical_match_gap_breakdown": [],
        "historical_replay_breakdown": [],
        "current_signal_group_breakdown": [],
        "top_status_messages": [],
        "recent_samples": [],
    }

    app.dependency_overrides.clear()


def test_research_overview_api_applies_provider_and_account_type_filters() -> None:
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
        openai_api = Account(
            source_id=source.id,
            auth_index="auth-openai-api",
            name="OpenAI-API",
            provider="openai",
            account_type="api",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=10),
            last_seen_at=base_time,
        )
        db.add_all([openai_hot, openai_ok, azure_hot, openai_api])
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
            ]
        )
        db.commit()

    response = asyncio.run(
        _request(
            "GET",
            "/api/v1/research/overview?window_days=7&provider=openai&account_type=chatgpt",
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "active_accounts": 2,
        "current_401_accounts": 1,
        "current_401_rate": 50.0,
        "became_401_events": 2,
        "affected_accounts": 1,
        "affected_provider_groups": 1,
        "sampled_previous_snapshots": 2,
    }
    assert payload["provider_account_type_breakdown"] == [
        {
            "label": "openai / chatgpt",
            "provider": "openai",
            "account_type": "chatgpt",
            "total_accounts": 2,
            "current_401_accounts": 1,
            "current_401_rate": 50.0,
            "became_401_events": 2,
            "affected_accounts": 1,
            "last_became_401_at": "2026-05-02T11:00:00Z",
        }
    ]
    hour_map = {
        item["hour_of_day"]: item["became_401_count"]
        for item in payload["event_hour_distribution"]
    }
    assert hour_map[11] == 1
    assert hour_map[12] == 1
    assert hour_map[10] == 0

    insights = payload["pre_401_insights"]
    assert insights["sampled_events"] == 2
    assert insights["events_with_previous_snapshot"] == 2
    assert insights["previous_to_event_gap_bands"] == [
        {"key": "lt_15m", "label": "15 分钟内", "count": 2},
        {"key": "15m_1h", "label": "15-60 分钟", "count": 0},
        {"key": "1h_6h", "label": "1-6 小时", "count": 0},
        {"key": "6h_24h", "label": "6-24 小时", "count": 0},
        {"key": "24h_plus", "label": "24 小时以上", "count": 0},
    ]
    assert insights["weekly_used_percent_bands"] == [
        {"key": "0_24", "label": "0-24%", "count": 0},
        {"key": "25_49", "label": "25-49%", "count": 0},
        {"key": "50_74", "label": "50-74%", "count": 0},
        {"key": "75_89", "label": "75-89%", "count": 0},
        {"key": "90_100", "label": "90-100%", "count": 1},
        {"key": "missing", "label": "未记录", "count": 1},
    ]
    assert insights["short_used_percent_bands"] == [
        {"key": "0_24", "label": "0-24%", "count": 0},
        {"key": "25_49", "label": "25-49%", "count": 0},
        {"key": "50_74", "label": "50-74%", "count": 0},
        {"key": "75_89", "label": "75-89%", "count": 1},
        {"key": "90_100", "label": "90-100%", "count": 0},
        {"key": "missing", "label": "未记录", "count": 1},
    ]
    assert {item["key"]: item["count"] for item in insights["signal_breakdown"]} == {
        "status_message_present": 2,
        "allowed_false": 1,
        "limit_reached": 1,
        "weekly_ge_90": 1,
    }
    assert insights["top_status_messages"] == [
        {"key": "soft_block", "label": "soft_block", "count": 1},
        {"key": "warmup", "label": "warmup", "count": 1},
    ]
    signal_comparison = {
        item["key"]: (
            item["pre_401_count"],
            item["pre_401_rate"],
            item["current_count"],
            item["current_rate"],
            item["rate_gap"],
        )
        for item in payload["signal_comparison"]
    }
    assert signal_comparison == {
        "weekly_ge_90": (1, 50.0, 0, 0.0, 50.0),
        "short_ge_90": (0, 0.0, 0, 0.0, 0.0),
        "limit_reached": (1, 50.0, 0, 0.0, 50.0),
        "allowed_false": (1, 50.0, 0, 0.0, 50.0),
        "remaining_empty": (0, 0.0, 0, 0.0, 0.0),
        "status_message_present": (2, 100.0, 0, 0.0, 100.0),
    }
    assert [item["event_id"] for item in payload["recent_event_samples"]] == [1, 3]
    assert payload["current_signal_baseline"] == {
        "observed_accounts": 1,
        "signal_accounts": 0,
        "signal_breakdown": [],
        "signal_pattern_breakdown": [],
        "signal_streak_breakdown": [],
        "historical_match_breakdown": [],
        "historical_match_gap_breakdown": [],
        "historical_replay_breakdown": [],
        "current_signal_group_breakdown": [],
        "top_status_messages": [],
        "recent_samples": [],
    }

    app.dependency_overrides.clear()


def test_research_overview_api_returns_current_signal_baseline_without_401_events() -> None:
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

        observed_signal = Account(
            source_id=source.id,
            auth_index="auth-signal",
            name="Signal-Account",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("97.00"),
            current_remaining=Decimal("3.00"),
            current_limit_reached=True,
            current_allowed=False,
            status_message='{"error":{"type":"usage_limit_reached","message":"usage limit reached on current window"}}',
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=3),
            last_seen_at=base_time,
        )
        observed_normal = Account(
            source_id=source.id,
            auth_index="auth-normal",
            name="Normal-Account",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=3),
            last_seen_at=base_time,
        )
        ignored_disabled = Account(
            source_id=source.id,
            auth_index="auth-disabled",
            name="Disabled-Account",
            provider="openai",
            account_type="chatgpt",
            disabled=True,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("99.00"),
            current_limit_reached=True,
            current_allowed=False,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=3),
            last_seen_at=base_time,
        )
        ignored_401 = Account(
            source_id=source.id,
            auth_index="auth-401",
            name="Hot-Account",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_weekly_used_percent=Decimal("100.00"),
            current_limit_reached=True,
            current_allowed=False,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=3),
            last_seen_at=base_time,
        )
        db.add_all([observed_signal, observed_normal, ignored_disabled, ignored_401])
        db.flush()
        db.add_all(
            [
                AccountSnapshot(
                    account_id=observed_signal.id,
                    scan_job_id=1,
                    checked_at=base_time,
                    created_at=base_time,
                    snapshot_status="success",
                    probe_status_code=200,
                    is_401=False,
                    weekly_used_percent=Decimal("97.00"),
                    remaining=Decimal("3.00"),
                    limit_reached=True,
                    allowed=False,
                    status_message='{"error":{"type":"usage_limit_reached","message":"usage limit reached on current window"}}',
                ),
                AccountSnapshot(
                    account_id=observed_signal.id,
                    scan_job_id=2,
                    checked_at=base_time - timedelta(hours=1),
                    created_at=base_time - timedelta(hours=1),
                    snapshot_status="success",
                    probe_status_code=200,
                    is_401=False,
                    weekly_used_percent=Decimal("96.00"),
                    remaining=Decimal("4.00"),
                    limit_reached=True,
                    allowed=False,
                    status_message="usage limit reached on current window",
                ),
                AccountSnapshot(
                    account_id=observed_signal.id,
                    scan_job_id=3,
                    checked_at=base_time - timedelta(hours=2),
                    created_at=base_time - timedelta(hours=2),
                    snapshot_status="success",
                    probe_status_code=200,
                    is_401=False,
                    weekly_used_percent=Decimal("95.00"),
                    remaining=Decimal("5.00"),
                    limit_reached=True,
                    allowed=False,
                    status_message="usage limit reached on current window",
                ),
                AccountSnapshot(
                    account_id=observed_signal.id,
                    scan_job_id=4,
                    checked_at=base_time - timedelta(hours=3),
                    created_at=base_time - timedelta(hours=3),
                    snapshot_status="success",
                    probe_status_code=200,
                    is_401=False,
                    weekly_used_percent=Decimal("80.00"),
                    remaining=Decimal("20.00"),
                    limit_reached=False,
                    allowed=True,
                    status_message=None,
                ),
                AccountSnapshot(
                    account_id=observed_signal.id,
                    scan_job_id=5,
                    checked_at=base_time + timedelta(minutes=30),
                    created_at=base_time + timedelta(minutes=30),
                    snapshot_status="failed",
                    probe_status_code=None,
                    is_401=False,
                    error_message="network timeout",
                ),
            ]
        )
        db.commit()

    response = asyncio.run(_request("GET", "/api/v1/research/overview?window_days=7"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["became_401_events"] == 0
    assert payload["recent_event_samples"] == []
    assert payload["signal_comparison"] == []
    assert payload["signal_pattern_comparison"] == []
    baseline = payload["current_signal_baseline"]
    assert baseline["observed_accounts"] == 2
    assert baseline["signal_accounts"] == 1
    assert {item["key"]: item["count"] for item in baseline["signal_breakdown"]} == {
        "weekly_ge_90": 1,
        "limit_reached": 1,
        "allowed_false": 1,
        "status_message_present": 1,
    }
    assert baseline["signal_pattern_breakdown"] == [
        {
            "key": "weekly_ge_90|limit_reached|allowed_false|status_message_present",
            "label": "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message",
            "count": 1,
        }
    ]
    assert baseline["signal_streak_breakdown"] == [
        {
            "key": "2_3",
            "label": "连续 2-3 轮",
            "count": 1,
        }
    ]
    assert baseline["historical_match_breakdown"] == [
        {
            "key": "no_history",
            "label": "暂无历史 401 样本",
            "count": 1,
        }
    ]
    assert baseline["current_signal_group_breakdown"] == [
        {
            "label": "openai / chatgpt",
            "provider": "openai",
            "account_type": "chatgpt",
            "observed_accounts": 2,
            "signal_accounts": 1,
            "signal_rate": 50.0,
            "multi_round_signal_accounts": 1,
            "historical_like_accounts": 0,
            "historical_like_rate": 0.0,
            "top_historical_gap_bucket": None,
            "top_historical_gap_label": None,
            "top_historical_gap_count": 0,
            "top_signal_pattern_key": "weekly_ge_90|limit_reached|allowed_false|status_message_present",
            "top_signal_pattern": "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message",
            "top_historical_like_samples": [],
        }
    ]
    assert baseline["top_status_messages"] == [
        {
            "key": "usage_limit_reached: usage limit reached on current window",
            "label": "usage_limit_reached: usage limit reached on current window",
            "count": 1,
        }
    ]
    assert baseline["recent_samples"] == [
        {
            "account_id": 1,
            "account_name": "Signal-Account",
            "provider": "openai",
            "account_type": "chatgpt",
            "current_last_checked_at": "2026-05-02T12:00:00Z",
            "current_weekly_used_percent": "97.00",
            "current_short_used_percent": None,
            "current_remaining": "3.00",
            "current_limit_reached": True,
            "current_allowed": False,
            "status_message_excerpt": "usage_limit_reached: usage limit reached on current window",
            "signal_labels": [
                "周额度 >= 90%",
                "limit_reached=true",
                "allowed=false",
                "存在 status_message",
            ],
            "consecutive_signal_snapshots": 3,
            "signal_started_at": "2026-05-02T10:00:00Z",
            "historical_match_level": "no_history",
            "historical_match_label": "暂无历史 401 样本",
            "historical_match_rate": 0.0,
            "historical_best_pattern": None,
            "historical_overlap_signal_labels": [],
            "historical_current_only_signal_labels": [],
            "historical_pattern_only_signal_labels": [],
            "historical_match_event_id": None,
            "historical_match_event_account_id": None,
            "historical_match_event_account_name": None,
            "historical_match_event_time": None,
            "historical_match_gap_bucket": None,
            "historical_match_gap_label": None,
            "historical_match_gap_minutes": None,
        }
    ]

    app.dependency_overrides.clear()


def test_research_overview_api_filters_current_signal_baseline() -> None:
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

        db.add_all(
            [
                Account(
                    source_id=source.id,
                    auth_index="auth-openai",
                    name="OpenAI-Signal",
                    provider="openai",
                    account_type="chatgpt",
                    disabled=False,
                    current_is_401=False,
                    current_status_code=200,
                    current_weekly_used_percent=Decimal("94.00"),
                    current_limit_reached=True,
                    current_allowed=False,
                    status_message="rate limit",
                    current_last_checked_at=base_time,
                    first_seen_at=base_time - timedelta(days=3),
                    last_seen_at=base_time,
                ),
                Account(
                    source_id=source.id,
                    auth_index="auth-azure",
                    name="Azure-Signal",
                    provider="azure",
                    account_type="chatgpt",
                    disabled=False,
                    current_is_401=False,
                    current_status_code=200,
                    current_weekly_used_percent=Decimal("96.00"),
                    current_limit_reached=True,
                    current_allowed=False,
                    status_message="busy window",
                    current_last_checked_at=base_time,
                    first_seen_at=base_time - timedelta(days=3),
                    last_seen_at=base_time,
                ),
            ]
        )
        db.commit()

    response = asyncio.run(_request("GET", "/api/v1/research/overview?window_days=7&provider=azure"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "active_accounts": 1,
        "current_401_accounts": 0,
        "current_401_rate": 0.0,
        "became_401_events": 0,
        "affected_accounts": 0,
        "affected_provider_groups": 0,
        "sampled_previous_snapshots": 0,
    }
    assert payload["provider_account_type_breakdown"] == [
        {
            "label": "azure / chatgpt",
            "provider": "azure",
            "account_type": "chatgpt",
            "total_accounts": 1,
            "current_401_accounts": 0,
            "current_401_rate": 0.0,
            "became_401_events": 0,
            "affected_accounts": 0,
            "last_became_401_at": None,
        }
    ]
    assert payload["recent_event_samples"] == []
    baseline = payload["current_signal_baseline"]
    assert baseline["observed_accounts"] == 1
    assert baseline["signal_accounts"] == 1
    assert {item["key"]: item["count"] for item in baseline["signal_breakdown"]} == {
        "allowed_false": 1,
        "limit_reached": 1,
        "status_message_present": 1,
        "weekly_ge_90": 1,
    }
    assert baseline["signal_pattern_breakdown"] == [
        {
            "key": "weekly_ge_90|limit_reached|allowed_false|status_message_present",
            "label": "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message",
            "count": 1,
        }
    ]
    assert baseline["signal_streak_breakdown"] == [
        {
            "key": "1",
            "label": "仅最新 1 轮",
            "count": 1,
        }
    ]
    assert baseline["historical_match_breakdown"] == [
        {
            "key": "no_history",
            "label": "暂无历史 401 样本",
            "count": 1,
        }
    ]
    assert baseline["current_signal_group_breakdown"] == [
        {
            "label": "azure / chatgpt",
            "provider": "azure",
            "account_type": "chatgpt",
            "observed_accounts": 1,
            "signal_accounts": 1,
            "signal_rate": 100.0,
            "multi_round_signal_accounts": 0,
            "historical_like_accounts": 0,
            "historical_like_rate": 0.0,
            "top_historical_gap_bucket": None,
            "top_historical_gap_label": None,
            "top_historical_gap_count": 0,
            "top_signal_pattern_key": "weekly_ge_90|limit_reached|allowed_false|status_message_present",
            "top_signal_pattern": "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message",
            "top_historical_like_samples": [],
        }
    ]
    assert baseline["top_status_messages"] == [
        {
            "key": "busy window",
            "label": "busy window",
            "count": 1,
        }
    ]
    assert baseline["recent_samples"] == [
        {
            "account_id": 2,
            "account_name": "Azure-Signal",
            "provider": "azure",
            "account_type": "chatgpt",
            "current_last_checked_at": "2026-05-02T12:00:00Z",
            "current_weekly_used_percent": "96.00",
            "current_short_used_percent": None,
            "current_remaining": None,
            "current_limit_reached": True,
            "current_allowed": False,
            "status_message_excerpt": "busy window",
            "signal_labels": [
                "周额度 >= 90%",
                "limit_reached=true",
                "allowed=false",
                "存在 status_message",
            ],
            "consecutive_signal_snapshots": 1,
            "signal_started_at": "2026-05-02T12:00:00Z",
            "historical_match_level": "no_history",
            "historical_match_label": "暂无历史 401 样本",
            "historical_match_rate": 0.0,
            "historical_best_pattern": None,
            "historical_overlap_signal_labels": [],
            "historical_current_only_signal_labels": [],
            "historical_pattern_only_signal_labels": [],
            "historical_match_event_id": None,
            "historical_match_event_account_id": None,
            "historical_match_event_account_name": None,
            "historical_match_event_time": None,
            "historical_match_gap_bucket": None,
            "historical_match_gap_label": None,
            "historical_match_gap_minutes": None,
        }
    ]

    app.dependency_overrides.clear()


def test_research_overview_api_applies_current_signal_key_filter() -> None:
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

        short_signal = Account(
            source_id=source.id,
            auth_index="auth-short",
            name="Short-Signal",
            provider="azure",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_short_used_percent=Decimal("92.00"),
            current_limit_reached=True,
            status_message="burst window",
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time,
        )
        weekly_signal = Account(
            source_id=source.id,
            auth_index="auth-weekly",
            name="Weekly-Signal",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("96.00"),
            current_limit_reached=True,
            current_allowed=False,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time,
        )
        normal_account = Account(
            source_id=source.id,
            auth_index="auth-normal",
            name="Normal-Account",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time,
        )
        db.add_all([short_signal, weekly_signal, normal_account])
        db.flush()
        db.add_all(
            [
                AccountSnapshot(
                    account_id=short_signal.id,
                    scan_job_id=1,
                    checked_at=base_time,
                    created_at=base_time,
                    snapshot_status="success",
                    probe_status_code=200,
                    is_401=False,
                    short_used_percent=Decimal("92.00"),
                    limit_reached=True,
                    status_message="burst window",
                ),
                AccountSnapshot(
                    account_id=short_signal.id,
                    scan_job_id=2,
                    checked_at=base_time - timedelta(hours=1),
                    created_at=base_time - timedelta(hours=1),
                    snapshot_status="success",
                    probe_status_code=200,
                    is_401=False,
                    short_used_percent=Decimal("91.00"),
                    limit_reached=True,
                    status_message="burst window",
                ),
                AccountSnapshot(
                    account_id=short_signal.id,
                    scan_job_id=3,
                    checked_at=base_time - timedelta(hours=2),
                    created_at=base_time - timedelta(hours=2),
                    snapshot_status="success",
                    probe_status_code=200,
                    is_401=False,
                    short_used_percent=Decimal("40.00"),
                    limit_reached=False,
                    status_message=None,
                ),
                AccountSnapshot(
                    account_id=weekly_signal.id,
                    scan_job_id=4,
                    checked_at=base_time,
                    created_at=base_time,
                    snapshot_status="success",
                    probe_status_code=200,
                    is_401=False,
                    weekly_used_percent=Decimal("96.00"),
                    limit_reached=True,
                    allowed=False,
                ),
            ]
        )
        db.commit()

    response = asyncio.run(
        _request("GET", "/api/v1/research/overview?window_days=7&current_signal_key=short_ge_90")
    )

    assert response.status_code == 200
    payload = response.json()
    baseline = payload["current_signal_baseline"]
    assert baseline["observed_accounts"] == 3
    assert baseline["signal_accounts"] == 1
    assert {item["key"]: item["count"] for item in baseline["signal_breakdown"]} == {
        "limit_reached": 1,
        "short_ge_90": 1,
        "status_message_present": 1,
    }
    assert baseline["signal_pattern_breakdown"] == [
        {
            "key": "short_ge_90|limit_reached|status_message_present",
            "label": "短周期 >= 90% / limit_reached=true / 存在 status_message",
            "count": 1,
        }
    ]
    assert baseline["signal_streak_breakdown"] == [
        {
            "key": "2_3",
            "label": "连续 2-3 轮",
            "count": 1,
        }
    ]
    assert baseline["historical_match_breakdown"] == [
        {
            "key": "no_history",
            "label": "暂无历史 401 样本",
            "count": 1,
        }
    ]
    assert baseline["current_signal_group_breakdown"] == [
        {
            "label": "azure / chatgpt",
            "provider": "azure",
            "account_type": "chatgpt",
            "observed_accounts": 1,
            "signal_accounts": 1,
            "signal_rate": 100.0,
            "multi_round_signal_accounts": 1,
            "historical_like_accounts": 0,
            "historical_like_rate": 0.0,
            "top_historical_gap_bucket": None,
            "top_historical_gap_label": None,
            "top_historical_gap_count": 0,
            "top_signal_pattern_key": "short_ge_90|limit_reached|status_message_present",
            "top_signal_pattern": "短周期 >= 90% / limit_reached=true / 存在 status_message",
            "top_historical_like_samples": [],
        }
    ]
    assert baseline["top_status_messages"] == [
        {
            "key": "burst window",
            "label": "burst window",
            "count": 1,
        }
    ]
    assert payload["signal_comparison"] == []
    assert payload["signal_pattern_comparison"] == []
    assert baseline["recent_samples"] == [
        {
            "account_id": 1,
            "account_name": "Short-Signal",
            "provider": "azure",
            "account_type": "chatgpt",
            "current_last_checked_at": "2026-05-02T12:00:00Z",
            "current_weekly_used_percent": None,
            "current_short_used_percent": "92.00",
            "current_remaining": None,
            "current_limit_reached": True,
            "current_allowed": None,
            "status_message_excerpt": "burst window",
            "signal_labels": [
                "短周期 >= 90%",
                "limit_reached=true",
                "存在 status_message",
            ],
            "consecutive_signal_snapshots": 2,
            "signal_started_at": "2026-05-02T11:00:00Z",
            "historical_match_level": "no_history",
            "historical_match_label": "暂无历史 401 样本",
            "historical_match_rate": 0.0,
            "historical_best_pattern": None,
            "historical_overlap_signal_labels": [],
            "historical_current_only_signal_labels": [],
            "historical_pattern_only_signal_labels": [],
            "historical_match_event_id": None,
            "historical_match_event_account_id": None,
            "historical_match_event_account_name": None,
            "historical_match_event_time": None,
            "historical_match_gap_bucket": None,
            "historical_match_gap_label": None,
            "historical_match_gap_minutes": None,
        }
    ]

    app.dependency_overrides.clear()


def test_research_overview_api_applies_current_signal_pattern_key_filter() -> None:
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

        db.add_all(
            [
                Account(
                    source_id=source.id,
                    auth_index="auth-short",
                    name="Short-Signal",
                    provider="azure",
                    account_type="chatgpt",
                    disabled=False,
                    current_is_401=False,
                    current_status_code=200,
                    current_short_used_percent=Decimal("92.00"),
                    current_limit_reached=True,
                    status_message="burst window",
                    current_last_checked_at=base_time,
                    first_seen_at=base_time - timedelta(days=2),
                    last_seen_at=base_time,
                ),
                Account(
                    source_id=source.id,
                    auth_index="auth-weekly",
                    name="Weekly-Signal",
                    provider="openai",
                    account_type="chatgpt",
                    disabled=False,
                    current_is_401=False,
                    current_status_code=200,
                    current_weekly_used_percent=Decimal("96.00"),
                    current_limit_reached=True,
                    current_allowed=False,
                    current_last_checked_at=base_time,
                    first_seen_at=base_time - timedelta(days=2),
                    last_seen_at=base_time,
                ),
            ]
        )
        db.commit()

    response = asyncio.run(
        _request(
            "GET",
            "/api/v1/research/overview?window_days=7&current_signal_pattern_key=status_message_present|short_ge_90|limit_reached",
        )
    )

    assert response.status_code == 200
    payload = response.json()
    baseline = payload["current_signal_baseline"]
    assert baseline["observed_accounts"] == 2
    assert baseline["signal_accounts"] == 1
    assert {item["key"]: item["count"] for item in baseline["signal_breakdown"]} == {
        "limit_reached": 1,
        "short_ge_90": 1,
        "status_message_present": 1,
    }
    assert baseline["signal_pattern_breakdown"] == [
        {
            "key": "short_ge_90|limit_reached|status_message_present",
            "label": "短周期 >= 90% / limit_reached=true / 存在 status_message",
            "count": 1,
        }
    ]
    assert baseline["current_signal_group_breakdown"] == [
        {
            "label": "azure / chatgpt",
            "provider": "azure",
            "account_type": "chatgpt",
            "observed_accounts": 1,
            "signal_accounts": 1,
            "signal_rate": 100.0,
            "multi_round_signal_accounts": 0,
            "historical_like_accounts": 0,
            "historical_like_rate": 0.0,
            "top_historical_gap_bucket": None,
            "top_historical_gap_label": None,
            "top_historical_gap_count": 0,
            "top_signal_pattern_key": "short_ge_90|limit_reached|status_message_present",
            "top_signal_pattern": "短周期 >= 90% / limit_reached=true / 存在 status_message",
            "top_historical_like_samples": [],
        }
    ]
    assert [item["account_name"] for item in baseline["recent_samples"]] == ["Short-Signal"]

    app.dependency_overrides.clear()


def test_research_overview_api_applies_pre_401_signal_key_filter() -> None:
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
            total_accounts=3,
            eligible_accounts=3,
            scanned_accounts=3,
            success_accounts=3,
            failed_accounts=0,
            new_401_events=2,
        )
        db.add(scan_job)
        db.flush()

        allowed_false_hot = Account(
            source_id=source.id,
            auth_index="auth-allowed-false",
            name="AllowedFalse-Hot",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=3),
            last_seen_at=base_time,
        )
        short_hot = Account(
            source_id=source.id,
            auth_index="auth-short-hot",
            name="Short-Hot",
            provider="azure",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=3),
            last_seen_at=base_time,
        )
        current_signal = Account(
            source_id=source.id,
            auth_index="auth-current-signal",
            name="Current-Signal",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("96.00"),
            current_limit_reached=True,
            current_allowed=False,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=3),
            last_seen_at=base_time,
        )
        db.add_all([allowed_false_hot, short_hot, current_signal])
        db.flush()

        allowed_false_snapshot = AccountSnapshot(
            account_id=allowed_false_hot.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=1, minutes=5),
            created_at=base_time - timedelta(hours=1, minutes=5),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("95.00"),
            short_used_percent=Decimal("88.00"),
            remaining=Decimal("2.00"),
            limit_reached=True,
            allowed=False,
            status_message="soft_block",
        )
        short_snapshot = AccountSnapshot(
            account_id=short_hot.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=2, minutes=5),
            created_at=base_time - timedelta(hours=2, minutes=5),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("50.00"),
            short_used_percent=Decimal("91.00"),
            remaining=Decimal("0.00"),
            limit_reached=False,
            allowed=True,
            status_message=None,
        )
        current_signal_snapshot = AccountSnapshot(
            account_id=current_signal.id,
            scan_job_id=scan_job.id,
            checked_at=base_time,
            created_at=base_time,
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("96.00"),
            limit_reached=True,
            allowed=False,
        )
        db.add_all([allowed_false_snapshot, short_snapshot, current_signal_snapshot])
        db.flush()

        db.add_all(
            [
                AccountEvent(
                    account_id=allowed_false_hot.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(hours=1),
                    related_snapshot_id=allowed_false_snapshot.id,
                    previous_snapshot_id=allowed_false_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(hours=1),
                ),
                AccountEvent(
                    account_id=short_hot.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(hours=2),
                    related_snapshot_id=short_snapshot.id,
                    previous_snapshot_id=short_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(hours=2),
                ),
            ]
        )
        db.commit()

    response = asyncio.run(
        _request("GET", "/api/v1/research/overview?window_days=7&pre_401_signal_key=allowed_false")
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["became_401_events"] == 2
    assert payload["summary"]["affected_accounts"] == 2
    assert payload["pre_401_insights"]["sampled_events"] == 1
    assert payload["pre_401_insights"]["events_with_previous_snapshot"] == 1
    assert {item["key"]: item["count"] for item in payload["pre_401_insights"]["signal_breakdown"]} == {
        "allowed_false": 1,
        "limit_reached": 1,
        "status_message_present": 1,
        "weekly_ge_90": 1,
    }
    assert payload["pre_401_insights"]["signal_pattern_breakdown"] == [
        {
            "key": "weekly_ge_90|limit_reached|allowed_false|status_message_present",
            "label": "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message",
            "count": 1,
        }
    ]
    assert payload["recent_event_samples"] == [
        {
            "event_id": 1,
            "account_id": 1,
            "account_name": "AllowedFalse-Hot",
            "provider": "openai",
            "account_type": "chatgpt",
            "event_time": "2026-05-02T11:00:00Z",
            "current_is_401": True,
            "previous_snapshot_id": 1,
            "previous_checked_at": "2026-05-02T10:55:00Z",
            "previous_to_event_gap_minutes": 5,
            "previous_weekly_used_percent": "95.00",
            "previous_short_used_percent": "88.00",
            "previous_remaining": "2.00",
            "previous_limit_reached": True,
            "previous_allowed": False,
            "previous_status_message": "soft_block",
        }
    ]
    signal_comparison = {
        item["key"]: (
            item["pre_401_count"],
            item["pre_401_rate"],
            item["current_count"],
            item["current_rate"],
            item["rate_gap"],
        )
        for item in payload["signal_comparison"]
    }
    assert signal_comparison == {
        "weekly_ge_90": (1, 50.0, 1, 100.0, -50.0),
        "short_ge_90": (1, 50.0, 0, 0.0, 50.0),
        "limit_reached": (1, 50.0, 1, 100.0, -50.0),
        "allowed_false": (1, 50.0, 1, 100.0, -50.0),
        "remaining_empty": (1, 50.0, 0, 0.0, 50.0),
        "status_message_present": (1, 50.0, 0, 0.0, 50.0),
    }
    signal_pattern_comparison = {
        item["key"]: (
            item["pre_401_count"],
            item["pre_401_rate"],
            item["current_count"],
            item["current_rate"],
            item["rate_gap"],
        )
        for item in payload["signal_pattern_comparison"]
    }
    assert signal_pattern_comparison == {
        "short_ge_90|remaining_empty": (1, 50.0, 0, 0.0, 50.0),
        "weekly_ge_90|limit_reached|allowed_false|status_message_present": (1, 50.0, 0, 0.0, 50.0),
        "weekly_ge_90|limit_reached|allowed_false": (0, 0.0, 1, 100.0, -100.0),
    }
    assert payload["current_signal_baseline"]["signal_accounts"] == 1

    app.dependency_overrides.clear()


def test_research_overview_api_applies_pre_401_signal_pattern_key_filter() -> None:
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
            total_accounts=2,
            eligible_accounts=2,
            scanned_accounts=2,
            success_accounts=2,
            failed_accounts=0,
            new_401_events=2,
        )
        db.add(scan_job)
        db.flush()

        allowed_false_hot = Account(
            source_id=source.id,
            auth_index="auth-allowed-false",
            name="AllowedFalse-Hot",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=3),
            last_seen_at=base_time,
        )
        short_hot = Account(
            source_id=source.id,
            auth_index="auth-short-hot",
            name="Short-Hot",
            provider="azure",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=3),
            last_seen_at=base_time,
        )
        db.add_all([allowed_false_hot, short_hot])
        db.flush()

        allowed_false_snapshot = AccountSnapshot(
            account_id=allowed_false_hot.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=1, minutes=5),
            created_at=base_time - timedelta(hours=1, minutes=5),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("95.00"),
            short_used_percent=Decimal("88.00"),
            remaining=Decimal("2.00"),
            limit_reached=True,
            allowed=False,
            status_message="soft_block",
        )
        short_snapshot = AccountSnapshot(
            account_id=short_hot.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=2, minutes=5),
            created_at=base_time - timedelta(hours=2, minutes=5),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("50.00"),
            short_used_percent=Decimal("91.00"),
            remaining=Decimal("0.00"),
            limit_reached=False,
            allowed=True,
            status_message=None,
        )
        db.add_all([allowed_false_snapshot, short_snapshot])
        db.flush()

        db.add_all(
            [
                AccountEvent(
                    account_id=allowed_false_hot.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(hours=1),
                    related_snapshot_id=allowed_false_snapshot.id,
                    previous_snapshot_id=allowed_false_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(hours=1),
                ),
                AccountEvent(
                    account_id=short_hot.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(hours=2),
                    related_snapshot_id=short_snapshot.id,
                    previous_snapshot_id=short_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(hours=2),
                ),
            ]
        )
        db.commit()

    response = asyncio.run(
        _request(
            "GET",
            "/api/v1/research/overview?window_days=7&pre_401_signal_pattern_key=allowed_false|status_message_present|limit_reached|weekly_ge_90",
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["became_401_events"] == 2
    assert payload["pre_401_insights"]["sampled_events"] == 1
    assert payload["pre_401_insights"]["events_with_previous_snapshot"] == 1
    assert payload["pre_401_insights"]["signal_pattern_breakdown"] == [
        {
            "key": "weekly_ge_90|limit_reached|allowed_false|status_message_present",
            "label": "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message",
            "count": 1,
        }
    ]
    assert [item["event_id"] for item in payload["recent_event_samples"]] == [1]

    app.dependency_overrides.clear()


def test_research_overview_api_applies_pre_401_gap_bucket_filter() -> None:
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
            scan_started_at=base_time - timedelta(hours=4),
            scan_finished_at=base_time - timedelta(hours=4) + timedelta(minutes=4),
            total_accounts=2,
            eligible_accounts=2,
            scanned_accounts=2,
            success_accounts=2,
            failed_accounts=0,
            new_401_events=2,
        )
        db.add(scan_job)
        db.flush()

        fresh_hot = Account(
            source_id=source.id,
            auth_index="auth-fresh-hot",
            name="Fresh-Hot",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=3),
            last_seen_at=base_time,
        )
        stale_hot = Account(
            source_id=source.id,
            auth_index="auth-stale-hot",
            name="Stale-Hot",
            provider="azure",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=3),
            last_seen_at=base_time,
        )
        db.add_all([fresh_hot, stale_hot])
        db.flush()

        fresh_snapshot = AccountSnapshot(
            account_id=fresh_hot.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=1, minutes=5),
            created_at=base_time - timedelta(hours=1, minutes=5),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("95.00"),
            short_used_percent=Decimal("88.00"),
            remaining=Decimal("2.00"),
            limit_reached=True,
            allowed=False,
            status_message="soft_block",
        )
        stale_snapshot = AccountSnapshot(
            account_id=stale_hot.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=3, minutes=30),
            created_at=base_time - timedelta(hours=3, minutes=30),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("50.00"),
            short_used_percent=Decimal("91.00"),
            remaining=Decimal("0.00"),
            limit_reached=False,
            allowed=True,
            status_message=None,
        )
        db.add_all([fresh_snapshot, stale_snapshot])
        db.flush()

        db.add_all(
            [
                AccountEvent(
                    account_id=fresh_hot.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(hours=1),
                    related_snapshot_id=fresh_snapshot.id,
                    previous_snapshot_id=fresh_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(hours=1),
                ),
                AccountEvent(
                    account_id=stale_hot.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(hours=2),
                    related_snapshot_id=stale_snapshot.id,
                    previous_snapshot_id=stale_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(hours=2),
                ),
            ]
        )
        db.commit()

    response = asyncio.run(
        _request("GET", "/api/v1/research/overview?window_days=7&pre_401_gap_bucket=lt_15m")
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["became_401_events"] == 2
    assert payload["summary"]["affected_accounts"] == 2
    assert payload["pre_401_insights"]["sampled_events"] == 1
    assert payload["pre_401_insights"]["events_with_previous_snapshot"] == 1
    assert payload["pre_401_insights"]["previous_to_event_gap_bands"] == [
        {"key": "lt_15m", "label": "15 分钟内", "count": 1},
        {"key": "15m_1h", "label": "15-60 分钟", "count": 0},
        {"key": "1h_6h", "label": "1-6 小时", "count": 0},
        {"key": "6h_24h", "label": "6-24 小时", "count": 0},
        {"key": "24h_plus", "label": "24 小时以上", "count": 0},
    ]
    assert {item["key"]: item["count"] for item in payload["pre_401_insights"]["signal_breakdown"]} == {
        "allowed_false": 1,
        "limit_reached": 1,
        "status_message_present": 1,
        "weekly_ge_90": 1,
    }
    assert payload["recent_event_samples"] == [
        {
            "event_id": 1,
            "account_id": 1,
            "account_name": "Fresh-Hot",
            "provider": "openai",
            "account_type": "chatgpt",
            "event_time": "2026-05-02T11:00:00Z",
            "current_is_401": True,
            "previous_snapshot_id": 1,
            "previous_checked_at": "2026-05-02T10:55:00Z",
            "previous_to_event_gap_minutes": 5,
            "previous_weekly_used_percent": "95.00",
            "previous_short_used_percent": "88.00",
            "previous_remaining": "2.00",
            "previous_limit_reached": True,
            "previous_allowed": False,
            "previous_status_message": "soft_block",
        }
    ]
    signal_comparison = {
        item["key"]: (
            item["pre_401_count"],
            item["pre_401_rate"],
            item["current_count"],
            item["current_rate"],
            item["rate_gap"],
        )
        for item in payload["signal_comparison"]
    }
    assert signal_comparison == {
        "weekly_ge_90": (1, 50.0, 0, 0.0, 50.0),
        "short_ge_90": (1, 50.0, 0, 0.0, 50.0),
        "limit_reached": (1, 50.0, 0, 0.0, 50.0),
        "allowed_false": (1, 50.0, 0, 0.0, 50.0),
        "remaining_empty": (1, 50.0, 0, 0.0, 50.0),
        "status_message_present": (1, 50.0, 0, 0.0, 50.0),
    }

    app.dependency_overrides.clear()


def test_research_overview_api_scores_current_samples_against_historical_patterns() -> None:
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
            scan_finished_at=base_time - timedelta(hours=3) + timedelta(minutes=4),
            total_accounts=6,
            eligible_accounts=6,
            scanned_accounts=6,
            success_accounts=6,
            failed_accounts=0,
            new_401_events=2,
        )
        db.add(scan_job)
        db.flush()

        historical_exact = Account(
            source_id=source.id,
            auth_index="auth-historical-exact",
            name="Historical-Exact",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=4),
            last_seen_at=base_time,
        )
        historical_short = Account(
            source_id=source.id,
            auth_index="auth-historical-short",
            name="Historical-Short",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=4),
            last_seen_at=base_time,
        )
        current_exact = Account(
            source_id=source.id,
            auth_index="auth-current-exact",
            name="Current-Exact",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("96.00"),
            current_limit_reached=True,
            current_allowed=False,
            status_message="same pattern",
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time,
        )
        current_covered = Account(
            source_id=source.id,
            auth_index="auth-current-covered",
            name="Current-Covered",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("94.00"),
            current_allowed=False,
            current_last_checked_at=base_time - timedelta(minutes=1),
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time,
        )
        current_partial = Account(
            source_id=source.id,
            auth_index="auth-current-partial",
            name="Current-Partial",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("92.00"),
            current_remaining=Decimal("0.00"),
            current_last_checked_at=base_time - timedelta(minutes=2),
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time,
        )
        current_no_overlap = Account(
            source_id=source.id,
            auth_index="auth-current-no-overlap",
            name="Current-No-Overlap",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_remaining=Decimal("0.00"),
            current_last_checked_at=base_time - timedelta(minutes=3),
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time,
        )
        db.add_all(
            [
                historical_exact,
                historical_short,
                current_exact,
                current_covered,
                current_partial,
                current_no_overlap,
            ]
        )
        db.flush()

        historical_exact_snapshot = AccountSnapshot(
            account_id=historical_exact.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=10),
            created_at=base_time - timedelta(minutes=10),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("95.00"),
            limit_reached=True,
            allowed=False,
            status_message="soft block",
        )
        historical_short_snapshot = AccountSnapshot(
            account_id=historical_short.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=20),
            created_at=base_time - timedelta(minutes=20),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            short_used_percent=Decimal("91.00"),
        )
        db.add_all([historical_exact_snapshot, historical_short_snapshot])
        db.flush()

        db.add_all(
            [
                AccountEvent(
                    account_id=historical_exact.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(minutes=5),
                    related_snapshot_id=historical_exact_snapshot.id,
                    previous_snapshot_id=historical_exact_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(minutes=5),
                ),
                AccountEvent(
                    account_id=historical_short.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(minutes=15),
                    related_snapshot_id=historical_short_snapshot.id,
                    previous_snapshot_id=historical_short_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(minutes=15),
                ),
            ]
        )
        db.commit()

    response = asyncio.run(_request("GET", "/api/v1/research/overview?window_days=7"))

    assert response.status_code == 200
    payload = response.json()
    baseline = payload["current_signal_baseline"]
    assert baseline["historical_match_breakdown"] == [
        {
            "key": "exact_pattern",
            "label": "与历史前序完全同模式",
            "count": 1,
        },
        {
            "key": "covered_pattern",
            "label": "被历史前序模式覆盖",
            "count": 1,
        },
        {
            "key": "partial_overlap",
            "label": "仅部分信号重合",
            "count": 1,
        },
        {
            "key": "no_overlap",
            "label": "与历史前序未重合",
            "count": 1,
        },
    ]
    assert baseline["historical_replay_breakdown"] == [
        {
            "event_id": 1,
            "event_account_id": 1,
            "event_account_name": "Historical-Exact",
            "event_time": "2026-05-02T11:55:00Z",
            "historical_best_pattern": "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message",
            "historical_gap_bucket": "lt_15m",
            "historical_gap_label": "15 分钟内",
            "historical_gap_minutes": 5,
            "matched_current_accounts": 3,
            "matched_current_rate": 75.0,
            "exact_match_accounts": 1,
            "covered_match_accounts": 1,
            "partial_overlap_accounts": 1,
        }
    ]
    assert baseline["current_signal_group_breakdown"] == [
        {
            "label": "openai / chatgpt",
            "provider": "openai",
            "account_type": "chatgpt",
            "observed_accounts": 4,
            "signal_accounts": 4,
            "signal_rate": 100.0,
            "multi_round_signal_accounts": 0,
            "historical_like_accounts": 2,
            "historical_like_rate": 50.0,
            "top_historical_gap_bucket": "lt_15m",
            "top_historical_gap_label": "15 分钟内",
            "top_historical_gap_count": 2,
            "top_signal_pattern_key": "remaining_empty",
            "top_signal_pattern": "remaining <= 0",
            "top_historical_like_samples": [
                {
                    "account_id": 3,
                    "account_name": "Current-Exact",
                    "current_last_checked_at": "2026-05-02T12:00:00Z",
                    "signal_labels": [
                        "周额度 >= 90%",
                        "limit_reached=true",
                        "allowed=false",
                        "存在 status_message",
                    ],
                    "consecutive_signal_snapshots": 1,
                    "historical_match_level": "exact_pattern",
                    "historical_match_label": "与历史前序完全同模式",
                    "historical_match_rate": 100.0,
                    "historical_best_pattern": "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message",
                    "historical_overlap_signal_labels": [
                        "周额度 >= 90%",
                        "limit_reached=true",
                        "allowed=false",
                        "存在 status_message",
                    ],
                    "historical_current_only_signal_labels": [],
                    "historical_pattern_only_signal_labels": [],
                    "historical_match_event_id": 1,
                    "historical_match_event_account_id": 1,
                    "historical_match_event_account_name": "Historical-Exact",
                    "historical_match_event_time": "2026-05-02T11:55:00Z",
                    "historical_match_gap_bucket": "lt_15m",
                    "historical_match_gap_label": "15 分钟内",
                    "historical_match_gap_minutes": 5,
                },
                {
                    "account_id": 4,
                    "account_name": "Current-Covered",
                    "current_last_checked_at": "2026-05-02T11:59:00Z",
                    "signal_labels": [
                        "周额度 >= 90%",
                        "allowed=false",
                    ],
                    "consecutive_signal_snapshots": 1,
                    "historical_match_level": "covered_pattern",
                    "historical_match_label": "被历史前序模式覆盖",
                    "historical_match_rate": 100.0,
                    "historical_best_pattern": "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message",
                    "historical_overlap_signal_labels": [
                        "周额度 >= 90%",
                        "allowed=false",
                    ],
                    "historical_current_only_signal_labels": [],
                    "historical_pattern_only_signal_labels": [
                        "limit_reached=true",
                        "存在 status_message",
                    ],
                    "historical_match_event_id": 1,
                    "historical_match_event_account_id": 1,
                    "historical_match_event_account_name": "Historical-Exact",
                    "historical_match_event_time": "2026-05-02T11:55:00Z",
                    "historical_match_gap_bucket": "lt_15m",
                    "historical_match_gap_label": "15 分钟内",
                    "historical_match_gap_minutes": 5,
                },
            ],
        }
    ]
    assert [item["account_name"] for item in baseline["recent_samples"]] == [
        "Current-Exact",
        "Current-Covered",
        "Current-Partial",
        "Current-No-Overlap",
    ]
    assert baseline["recent_samples"][0]["historical_match_level"] == "exact_pattern"
    assert baseline["recent_samples"][0]["historical_match_rate"] == 100.0
    assert (
        baseline["recent_samples"][0]["historical_best_pattern"]
        == "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message"
    )
    assert baseline["recent_samples"][0]["historical_overlap_signal_labels"] == [
        "周额度 >= 90%",
        "limit_reached=true",
        "allowed=false",
        "存在 status_message",
    ]
    assert baseline["recent_samples"][0]["historical_current_only_signal_labels"] == []
    assert baseline["recent_samples"][0]["historical_pattern_only_signal_labels"] == []
    assert baseline["recent_samples"][0]["historical_match_event_id"] == 1
    assert baseline["recent_samples"][0]["historical_match_event_account_id"] == 1
    assert baseline["recent_samples"][0]["historical_match_event_account_name"] == "Historical-Exact"
    assert baseline["recent_samples"][0]["historical_match_event_time"] == "2026-05-02T11:55:00Z"
    assert baseline["recent_samples"][1]["historical_match_level"] == "covered_pattern"
    assert baseline["recent_samples"][1]["historical_match_rate"] == 100.0
    assert baseline["recent_samples"][1]["historical_overlap_signal_labels"] == [
        "周额度 >= 90%",
        "allowed=false",
    ]
    assert baseline["recent_samples"][1]["historical_current_only_signal_labels"] == []
    assert baseline["recent_samples"][1]["historical_pattern_only_signal_labels"] == [
        "limit_reached=true",
        "存在 status_message",
    ]
    assert baseline["recent_samples"][1]["historical_match_event_id"] == 1
    assert baseline["recent_samples"][1]["historical_match_event_account_name"] == "Historical-Exact"
    assert baseline["recent_samples"][2]["historical_match_level"] == "partial_overlap"
    assert baseline["recent_samples"][2]["historical_match_rate"] == 50.0
    assert baseline["recent_samples"][2]["historical_overlap_signal_labels"] == ["周额度 >= 90%"]
    assert baseline["recent_samples"][2]["historical_current_only_signal_labels"] == ["remaining <= 0"]
    assert baseline["recent_samples"][2]["historical_pattern_only_signal_labels"] == [
        "limit_reached=true",
        "allowed=false",
        "存在 status_message",
    ]
    assert baseline["recent_samples"][2]["historical_match_event_id"] == 1
    assert baseline["recent_samples"][2]["historical_match_event_account_name"] == "Historical-Exact"
    assert baseline["recent_samples"][3] == {
        "account_id": 6,
        "account_name": "Current-No-Overlap",
        "provider": "openai",
        "account_type": "chatgpt",
        "current_last_checked_at": "2026-05-02T11:57:00Z",
        "current_weekly_used_percent": None,
        "current_short_used_percent": None,
        "current_remaining": "0.00",
        "current_limit_reached": None,
        "current_allowed": None,
        "status_message_excerpt": None,
        "signal_labels": ["remaining <= 0"],
        "consecutive_signal_snapshots": 1,
        "signal_started_at": "2026-05-02T11:57:00Z",
        "historical_match_level": "no_overlap",
        "historical_match_label": "与历史前序未重合",
        "historical_match_rate": 0.0,
        "historical_best_pattern": None,
        "historical_overlap_signal_labels": [],
        "historical_current_only_signal_labels": [],
        "historical_pattern_only_signal_labels": [],
        "historical_match_event_id": None,
        "historical_match_event_account_id": None,
        "historical_match_event_account_name": None,
        "historical_match_event_time": None,
        "historical_match_gap_bucket": None,
        "historical_match_gap_label": None,
        "historical_match_gap_minutes": None,
    }

    app.dependency_overrides.clear()


def test_research_overview_api_prefers_latest_historical_event_for_same_pattern_replay() -> None:
    session_factory = _create_session_factory()
    base_time = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)

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
            source_key="main",
            source_name="Main Source",
            base_url="http://localhost:8787",
            created_at=base_time,
            updated_at=base_time,
        )
        db.add(source)
        db.flush()

        scan_job = ScanJob(
            source_id=source.id,
            trigger_mode="manual",
            status="success",
            scan_started_at=base_time,
            scan_finished_at=base_time,
            created_at=base_time,
            updated_at=base_time,
            total_accounts=3,
            eligible_accounts=3,
            scanned_accounts=3,
            success_accounts=3,
            failed_accounts=0,
            new_401_events=2,
        )
        db.add(scan_job)
        db.flush()

        older_historical = Account(
            source_id=source.id,
            auth_index="auth-historical-older",
            name="Historical-Older",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=5),
            last_seen_at=base_time,
        )
        latest_historical = Account(
            source_id=source.id,
            auth_index="auth-historical-latest",
            name="Historical-Latest",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=4),
            last_seen_at=base_time,
        )
        current_account = Account(
            source_id=source.id,
            auth_index="auth-current",
            name="Current-Replay",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("96.00"),
            current_limit_reached=True,
            current_allowed=False,
            status_message="same pattern",
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time,
        )
        db.add_all([older_historical, latest_historical, current_account])
        db.flush()

        older_snapshot = AccountSnapshot(
            account_id=older_historical.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=40),
            created_at=base_time - timedelta(minutes=40),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("95.00"),
            limit_reached=True,
            allowed=False,
            status_message="older sample",
        )
        latest_snapshot = AccountSnapshot(
            account_id=latest_historical.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=20),
            created_at=base_time - timedelta(minutes=20),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("94.00"),
            limit_reached=True,
            allowed=False,
            status_message="latest sample",
        )
        db.add_all([older_snapshot, latest_snapshot])
        db.flush()

        db.add_all(
            [
                AccountEvent(
                    account_id=older_historical.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(minutes=30),
                    related_snapshot_id=older_snapshot.id,
                    previous_snapshot_id=older_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(minutes=30),
                ),
                AccountEvent(
                    account_id=latest_historical.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(minutes=10),
                    related_snapshot_id=latest_snapshot.id,
                    previous_snapshot_id=latest_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(minutes=10),
                ),
            ]
        )
        db.commit()

    response = asyncio.run(_request("GET", "/api/v1/research/overview?window_days=7"))

    assert response.status_code == 200
    sample = response.json()["current_signal_baseline"]["recent_samples"][0]
    assert sample["account_name"] == "Current-Replay"
    assert sample["historical_match_level"] == "exact_pattern"
    assert sample["historical_match_event_id"] == 2
    assert sample["historical_match_event_account_id"] == 2
    assert sample["historical_match_event_account_name"] == "Historical-Latest"
    assert sample["historical_match_event_time"] == "2026-05-02T11:50:00Z"
    assert sample["historical_match_gap_bucket"] == "lt_15m"
    assert sample["historical_match_gap_label"] == "15 分钟内"
    assert sample["historical_match_gap_minutes"] == 10

    app.dependency_overrides.clear()


def test_research_overview_api_filters_current_baseline_by_historical_event_id() -> None:
    session_factory = _create_session_factory()
    base_time = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)

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
            source_key="main",
            source_name="Main Source",
            base_url="http://localhost:8787",
            created_at=base_time,
            updated_at=base_time,
        )
        db.add(source)
        db.flush()

        scan_job = ScanJob(
            source_id=source.id,
            trigger_mode="manual",
            status="success",
            scan_started_at=base_time,
            scan_finished_at=base_time,
            created_at=base_time,
            updated_at=base_time,
            total_accounts=4,
            eligible_accounts=4,
            scanned_accounts=4,
            success_accounts=4,
            failed_accounts=0,
            new_401_events=2,
        )
        db.add(scan_job)
        db.flush()

        historical_one = Account(
            source_id=source.id,
            auth_index="auth-historical-one",
            name="Historical-One",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=5),
            last_seen_at=base_time,
        )
        historical_two = Account(
            source_id=source.id,
            auth_index="auth-historical-two",
            name="Historical-Two",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=4),
            last_seen_at=base_time,
        )
        current_one = Account(
            source_id=source.id,
            auth_index="auth-current-one",
            name="Current-One",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("95.00"),
            current_allowed=False,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time,
        )
        current_two = Account(
            source_id=source.id,
            auth_index="auth-current-two",
            name="Current-Two",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_short_used_percent=Decimal("96.00"),
            current_limit_reached=True,
            current_last_checked_at=base_time - timedelta(minutes=1),
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time,
        )
        db.add_all([historical_one, historical_two, current_one, current_two])
        db.flush()

        snapshot_one = AccountSnapshot(
            account_id=historical_one.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=25),
            created_at=base_time - timedelta(minutes=25),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("94.00"),
            allowed=False,
        )
        snapshot_two = AccountSnapshot(
            account_id=historical_two.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=2),
            created_at=base_time - timedelta(hours=2),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            short_used_percent=Decimal("95.00"),
            limit_reached=True,
        )
        db.add_all([snapshot_one, snapshot_two])
        db.flush()

        db.add_all(
            [
                AccountEvent(
                    account_id=historical_one.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(minutes=20),
                    related_snapshot_id=snapshot_one.id,
                    previous_snapshot_id=snapshot_one.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(minutes=20),
                ),
                AccountEvent(
                    account_id=historical_two.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(minutes=10),
                    related_snapshot_id=snapshot_two.id,
                    previous_snapshot_id=snapshot_two.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(minutes=10),
                ),
            ]
        )
        db.commit()

    response = asyncio.run(
        _request(
            "GET",
            "/api/v1/research/overview?window_days=7&current_historical_event_id=2",
        )
    )

    assert response.status_code == 200
    baseline = response.json()["current_signal_baseline"]
    assert baseline["signal_accounts"] == 1
    assert baseline["historical_match_breakdown"] == [
        {
            "key": "exact_pattern",
            "label": "与历史前序完全同模式",
            "count": 1,
        }
    ]
    assert baseline["historical_replay_breakdown"] == [
        {
            "event_id": 2,
            "event_account_id": 2,
            "event_account_name": "Historical-Two",
            "event_time": "2026-05-02T11:50:00Z",
            "historical_best_pattern": "短周期 >= 90% / limit_reached=true",
            "historical_gap_bucket": "1h_6h",
            "historical_gap_label": "1-6 小时",
            "historical_gap_minutes": 110,
            "matched_current_accounts": 1,
            "matched_current_rate": 100.0,
            "exact_match_accounts": 1,
            "covered_match_accounts": 0,
            "partial_overlap_accounts": 0,
        }
    ]
    assert [item["account_name"] for item in baseline["recent_samples"]] == ["Current-Two"]
    assert baseline["recent_samples"][0]["historical_match_event_id"] == 2
    assert baseline["recent_samples"][0]["historical_match_event_account_name"] == "Historical-Two"

    app.dependency_overrides.clear()


def test_research_overview_api_filters_current_baseline_by_match_level_and_streak() -> None:
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
            scan_started_at=base_time - timedelta(hours=2),
            scan_finished_at=base_time - timedelta(hours=2) + timedelta(minutes=5),
            total_accounts=4,
            eligible_accounts=4,
            scanned_accounts=4,
            success_accounts=4,
            failed_accounts=0,
            new_401_events=1,
        )
        db.add(scan_job)
        db.flush()

        historical_exact = Account(
            source_id=source.id,
            auth_index="historical-exact",
            name="Historical-Exact",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time - timedelta(minutes=5),
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time - timedelta(minutes=5),
        )
        current_exact_streak_two = Account(
            source_id=source.id,
            auth_index="current-exact-streak-two",
            name="Current-Exact-Streak-Two",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("95.00"),
            current_limit_reached=True,
            current_allowed=False,
            status_message="same pattern",
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=1),
            last_seen_at=base_time,
        )
        current_exact_streak_one = Account(
            source_id=source.id,
            auth_index="current-exact-streak-one",
            name="Current-Exact-Streak-One",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("94.00"),
            current_limit_reached=True,
            current_allowed=False,
            status_message="same pattern",
            current_last_checked_at=base_time - timedelta(minutes=1),
            first_seen_at=base_time - timedelta(days=1),
            last_seen_at=base_time - timedelta(minutes=1),
        )
        current_covered_streak_three = Account(
            source_id=source.id,
            auth_index="current-covered-streak-three",
            name="Current-Covered-Streak-Three",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("93.00"),
            current_allowed=False,
            current_last_checked_at=base_time - timedelta(minutes=2),
            first_seen_at=base_time - timedelta(days=1),
            last_seen_at=base_time - timedelta(minutes=2),
        )
        db.add_all(
            [
                historical_exact,
                current_exact_streak_two,
                current_exact_streak_one,
                current_covered_streak_three,
            ]
        )
        db.flush()

        historical_snapshot = AccountSnapshot(
            account_id=historical_exact.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=15),
            created_at=base_time - timedelta(minutes=15),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("95.00"),
            limit_reached=True,
            allowed=False,
            status_message="history sample",
        )
        current_exact_snapshot_latest = AccountSnapshot(
            account_id=current_exact_streak_two.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=10),
            created_at=base_time - timedelta(minutes=10),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("94.00"),
            limit_reached=True,
            allowed=False,
            status_message="same pattern",
        )
        current_exact_snapshot_previous = AccountSnapshot(
            account_id=current_exact_streak_two.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=20),
            created_at=base_time - timedelta(minutes=20),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("93.00"),
            limit_reached=True,
            allowed=False,
            status_message="same pattern",
        )
        current_covered_snapshot_latest = AccountSnapshot(
            account_id=current_covered_streak_three.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=8),
            created_at=base_time - timedelta(minutes=8),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("93.00"),
            allowed=False,
        )
        current_covered_snapshot_middle = AccountSnapshot(
            account_id=current_covered_streak_three.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=18),
            created_at=base_time - timedelta(minutes=18),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("92.00"),
            allowed=False,
        )
        current_covered_snapshot_oldest = AccountSnapshot(
            account_id=current_covered_streak_three.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=28),
            created_at=base_time - timedelta(minutes=28),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("91.00"),
            allowed=False,
        )
        db.add_all(
            [
                historical_snapshot,
                current_exact_snapshot_latest,
                current_exact_snapshot_previous,
                current_covered_snapshot_latest,
                current_covered_snapshot_middle,
                current_covered_snapshot_oldest,
            ]
        )
        db.flush()

        db.add(
            AccountEvent(
                account_id=historical_exact.id,
                event_type="became_401",
                event_time=base_time - timedelta(minutes=5),
                related_snapshot_id=historical_snapshot.id,
                previous_snapshot_id=historical_snapshot.id,
                from_status_code=200,
                to_status_code=401,
                from_is_401=False,
                to_is_401=True,
                from_disabled=False,
                to_disabled=False,
                created_at=base_time - timedelta(minutes=5),
            )
        )
        db.commit()

    response = asyncio.run(
        _request(
            "GET",
            "/api/v1/research/overview?window_days=7&current_match_level=exact_pattern&current_signal_min_streak=2",
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["became_401_events"] == 1
    assert payload["pre_401_insights"]["sampled_events"] == 1
    baseline = payload["current_signal_baseline"]
    assert baseline["observed_accounts"] == 3
    assert baseline["signal_accounts"] == 1
    assert baseline["historical_match_breakdown"] == [
        {
            "key": "exact_pattern",
            "label": "与历史前序完全同模式",
            "count": 1,
        }
    ]
    assert baseline["historical_match_gap_breakdown"] == [
        {"key": "lt_15m", "label": "15 分钟内", "count": 1},
        {"key": "15m_1h", "label": "15-60 分钟", "count": 0},
        {"key": "1h_6h", "label": "1-6 小时", "count": 0},
        {"key": "6h_24h", "label": "6-24 小时", "count": 0},
        {"key": "24h_plus", "label": "24 小时以上", "count": 0},
    ]
    assert baseline["signal_streak_breakdown"] == [
        {
            "key": "2_3",
            "label": "连续 2-3 轮",
            "count": 1,
        }
    ]
    assert baseline["current_signal_group_breakdown"] == [
        {
            "label": "openai / chatgpt",
            "provider": "openai",
            "account_type": "chatgpt",
            "observed_accounts": 3,
            "signal_accounts": 1,
            "signal_rate": 33.33,
            "multi_round_signal_accounts": 1,
            "historical_like_accounts": 1,
            "historical_like_rate": 100.0,
            "top_historical_gap_bucket": "lt_15m",
            "top_historical_gap_label": "15 分钟内",
            "top_historical_gap_count": 1,
            "top_signal_pattern_key": "weekly_ge_90|limit_reached|allowed_false|status_message_present",
            "top_signal_pattern": "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message",
            "top_historical_like_samples": [
                {
                    "account_id": 2,
                    "account_name": "Current-Exact-Streak-Two",
                    "current_last_checked_at": "2026-05-02T12:00:00Z",
                    "signal_labels": [
                        "周额度 >= 90%",
                        "limit_reached=true",
                        "allowed=false",
                        "存在 status_message",
                    ],
                    "consecutive_signal_snapshots": 2,
                    "historical_match_level": "exact_pattern",
                    "historical_match_label": "与历史前序完全同模式",
                    "historical_match_rate": 100.0,
                    "historical_best_pattern": "周额度 >= 90% / limit_reached=true / allowed=false / 存在 status_message",
                    "historical_overlap_signal_labels": [
                        "周额度 >= 90%",
                        "limit_reached=true",
                        "allowed=false",
                        "存在 status_message",
                    ],
                    "historical_current_only_signal_labels": [],
                    "historical_pattern_only_signal_labels": [],
                    "historical_match_event_id": 1,
                    "historical_match_event_account_id": 1,
                    "historical_match_event_account_name": "Historical-Exact",
                    "historical_match_event_time": "2026-05-02T11:55:00Z",
                    "historical_match_gap_bucket": "lt_15m",
                    "historical_match_gap_label": "15 分钟内",
                    "historical_match_gap_minutes": 10,
                }
            ],
        }
    ]
    assert [item["account_name"] for item in baseline["recent_samples"]] == [
        "Current-Exact-Streak-Two",
    ]
    assert baseline["recent_samples"][0]["consecutive_signal_snapshots"] == 2
    assert baseline["recent_samples"][0]["historical_match_level"] == "exact_pattern"
    assert baseline["recent_samples"][0]["historical_match_gap_bucket"] == "lt_15m"
    assert baseline["recent_samples"][0]["historical_match_gap_label"] == "15 分钟内"
    assert baseline["recent_samples"][0]["historical_match_gap_minutes"] == 10
    assert baseline["recent_samples"][0]["historical_overlap_signal_labels"] == [
        "周额度 >= 90%",
        "limit_reached=true",
        "allowed=false",
        "存在 status_message",
    ]
    assert baseline["recent_samples"][0]["historical_current_only_signal_labels"] == []
    assert baseline["recent_samples"][0]["historical_pattern_only_signal_labels"] == []

    app.dependency_overrides.clear()


def test_research_overview_api_filters_current_baseline_by_historical_gap_bucket() -> None:
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
            scan_finished_at=base_time - timedelta(hours=3) + timedelta(minutes=5),
            total_accounts=4,
            eligible_accounts=4,
            scanned_accounts=4,
            success_accounts=4,
            failed_accounts=0,
            new_401_events=2,
        )
        db.add(scan_job)
        db.flush()

        historical_fresh = Account(
            source_id=source.id,
            auth_index="historical-fresh",
            name="Historical-Fresh",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time - timedelta(minutes=5),
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time - timedelta(minutes=5),
        )
        historical_stale = Account(
            source_id=source.id,
            auth_index="historical-stale",
            name="Historical-Stale",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time - timedelta(minutes=10),
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time - timedelta(minutes=10),
        )
        current_fresh = Account(
            source_id=source.id,
            auth_index="current-fresh",
            name="Current-Fresh",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("94.00"),
            current_limit_reached=True,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=1),
            last_seen_at=base_time,
        )
        current_stale = Account(
            source_id=source.id,
            auth_index="current-stale",
            name="Current-Stale",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_short_used_percent=Decimal("91.00"),
            current_allowed=False,
            current_last_checked_at=base_time - timedelta(minutes=1),
            first_seen_at=base_time - timedelta(days=1),
            last_seen_at=base_time - timedelta(minutes=1),
        )
        db.add_all([historical_fresh, historical_stale, current_fresh, current_stale])
        db.flush()

        historical_fresh_snapshot = AccountSnapshot(
            account_id=historical_fresh.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=15),
            created_at=base_time - timedelta(minutes=15),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("96.00"),
            limit_reached=True,
        )
        historical_stale_snapshot = AccountSnapshot(
            account_id=historical_stale.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=2, minutes=10),
            created_at=base_time - timedelta(hours=2, minutes=10),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            short_used_percent=Decimal("92.00"),
            allowed=False,
            status_message="history sample",
        )
        current_fresh_snapshot = AccountSnapshot(
            account_id=current_fresh.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=8),
            created_at=base_time - timedelta(minutes=8),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("94.00"),
            limit_reached=True,
        )
        current_stale_snapshot = AccountSnapshot(
            account_id=current_stale.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=7),
            created_at=base_time - timedelta(minutes=7),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            short_used_percent=Decimal("91.00"),
            allowed=False,
        )
        db.add_all(
            [
                historical_fresh_snapshot,
                historical_stale_snapshot,
                current_fresh_snapshot,
                current_stale_snapshot,
            ]
        )
        db.flush()

        db.add_all(
            [
                AccountEvent(
                    account_id=historical_fresh.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(minutes=5),
                    related_snapshot_id=historical_fresh_snapshot.id,
                    previous_snapshot_id=historical_fresh_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(minutes=5),
                ),
                AccountEvent(
                    account_id=historical_stale.id,
                    event_type="became_401",
                    event_time=base_time,
                    related_snapshot_id=historical_stale_snapshot.id,
                    previous_snapshot_id=historical_stale_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time,
                ),
            ]
        )
        db.commit()

    response = asyncio.run(
        _request(
            "GET",
            "/api/v1/research/overview?window_days=7&current_historical_gap_bucket=lt_15m",
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["became_401_events"] == 2
    baseline = payload["current_signal_baseline"]
    assert baseline["observed_accounts"] == 2
    assert baseline["signal_accounts"] == 1
    assert baseline["historical_match_breakdown"] == [
        {
            "key": "exact_pattern",
            "label": "与历史前序完全同模式",
            "count": 1,
        }
    ]
    assert baseline["historical_match_gap_breakdown"] == [
        {"key": "lt_15m", "label": "15 分钟内", "count": 1},
        {"key": "15m_1h", "label": "15-60 分钟", "count": 0},
        {"key": "1h_6h", "label": "1-6 小时", "count": 0},
        {"key": "6h_24h", "label": "6-24 小时", "count": 0},
        {"key": "24h_plus", "label": "24 小时以上", "count": 0},
    ]
    assert [item["account_name"] for item in baseline["recent_samples"]] == ["Current-Fresh"]
    assert baseline["recent_samples"][0]["historical_match_gap_bucket"] == "lt_15m"
    assert baseline["recent_samples"][0]["historical_match_gap_minutes"] == 10

    app.dependency_overrides.clear()


def test_research_overview_api_rejects_unknown_current_signal_key() -> None:
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

    response = asyncio.run(
        _request("GET", "/api/v1/research/overview?window_days=7&current_signal_key=unknown_signal")
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported current_signal_key: unknown_signal"

    app.dependency_overrides.clear()


def test_research_overview_api_rejects_unknown_current_signal_pattern_key() -> None:
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

    response = asyncio.run(
        _request(
            "GET",
            "/api/v1/research/overview?window_days=7&current_signal_pattern_key=unknown_signal|limit_reached",
        )
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Unsupported current_signal_pattern_key: unknown_signal|limit_reached"
    )

    app.dependency_overrides.clear()


def test_research_overview_api_rejects_unknown_current_match_level() -> None:
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

    response = asyncio.run(
        _request("GET", "/api/v1/research/overview?window_days=7&current_match_level=unknown_level")
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported current_match_level: unknown_level"

    app.dependency_overrides.clear()


def test_research_overview_api_rejects_unknown_current_historical_gap_bucket() -> None:
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

    response = asyncio.run(
        _request("GET", "/api/v1/research/overview?window_days=7&current_historical_gap_bucket=unknown_gap")
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported current_historical_gap_bucket: unknown_gap"

    app.dependency_overrides.clear()


def test_research_overview_api_rejects_unknown_pre_401_signal_key() -> None:
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

    response = asyncio.run(
        _request("GET", "/api/v1/research/overview?window_days=7&pre_401_signal_key=unknown_signal")
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported pre_401_signal_key: unknown_signal"

    app.dependency_overrides.clear()


def test_research_overview_api_rejects_unknown_pre_401_signal_pattern_key() -> None:
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

    response = asyncio.run(
        _request(
            "GET",
            "/api/v1/research/overview?window_days=7&pre_401_signal_pattern_key=weekly_ge_90|weekly_ge_90",
        )
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Unsupported pre_401_signal_pattern_key: weekly_ge_90|weekly_ge_90"
    )

    app.dependency_overrides.clear()


def test_research_overview_api_rejects_unknown_pre_401_gap_bucket() -> None:
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

    response = asyncio.run(
        _request("GET", "/api/v1/research/overview?window_days=7&pre_401_gap_bucket=unknown_gap")
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported pre_401_gap_bucket: unknown_gap"

    app.dependency_overrides.clear()


def test_research_overview_api_stabilizes_group_top_pattern_on_tie() -> None:
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

        db.add_all(
            [
                Account(
                    source_id=source.id,
                    auth_index="auth-allowed",
                    name="Allowed-Signal",
                    provider="openai",
                    account_type="chatgpt",
                    disabled=False,
                    current_is_401=False,
                    current_status_code=200,
                    current_allowed=False,
                    current_last_checked_at=base_time,
                    first_seen_at=base_time - timedelta(days=1),
                    last_seen_at=base_time,
                ),
                Account(
                    source_id=source.id,
                    auth_index="auth-limit",
                    name="Limit-Signal",
                    provider="openai",
                    account_type="chatgpt",
                    disabled=False,
                    current_is_401=False,
                    current_status_code=200,
                    current_limit_reached=True,
                    current_last_checked_at=base_time,
                    first_seen_at=base_time - timedelta(days=1),
                    last_seen_at=base_time,
                ),
            ]
        )
        db.commit()

    response = asyncio.run(_request("GET", "/api/v1/research/overview?window_days=7"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_signal_baseline"]["current_signal_group_breakdown"] == [
        {
            "label": "openai / chatgpt",
            "provider": "openai",
            "account_type": "chatgpt",
            "observed_accounts": 2,
            "signal_accounts": 2,
            "signal_rate": 100.0,
            "multi_round_signal_accounts": 0,
            "historical_like_accounts": 0,
            "historical_like_rate": 0.0,
            "top_historical_gap_bucket": None,
            "top_historical_gap_label": None,
            "top_historical_gap_count": 0,
            "top_signal_pattern_key": "allowed_false",
            "top_signal_pattern": "allowed=false",
            "top_historical_like_samples": [],
        }
    ]

    app.dependency_overrides.clear()


def test_research_overview_api_prioritizes_groups_with_more_historical_like_samples() -> None:
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
            scan_started_at=base_time - timedelta(hours=1),
            scan_finished_at=base_time - timedelta(minutes=55),
            total_accounts=5,
            eligible_accounts=5,
            scanned_accounts=5,
            success_accounts=5,
            failed_accounts=0,
            new_401_events=1,
        )
        db.add(scan_job)
        db.flush()

        historical_account = Account(
            source_id=source.id,
            auth_index="historical-openai",
            name="Historical-OpenAI",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time - timedelta(minutes=5),
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time - timedelta(minutes=5),
        )
        current_openai = Account(
            source_id=source.id,
            auth_index="current-openai",
            name="Current-OpenAI-Exact",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("95.00"),
            current_limit_reached=True,
            current_allowed=False,
            status_message="still hot",
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=1),
            last_seen_at=base_time,
        )
        current_azure_one = Account(
            source_id=source.id,
            auth_index="current-azure-one",
            name="Current-Azure-One",
            provider="azure",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_short_used_percent=Decimal("93.00"),
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=1),
            last_seen_at=base_time,
        )
        current_azure_two = Account(
            source_id=source.id,
            auth_index="current-azure-two",
            name="Current-Azure-Two",
            provider="azure",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_remaining=Decimal("0.00"),
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=1),
            last_seen_at=base_time,
        )
        db.add_all([historical_account, current_openai, current_azure_one, current_azure_two])
        db.flush()

        historical_snapshot = AccountSnapshot(
            account_id=historical_account.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=15),
            created_at=base_time - timedelta(minutes=15),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("95.00"),
            limit_reached=True,
            allowed=False,
            status_message="history hot",
        )
        db.add(historical_snapshot)
        db.flush()

        db.add(
            AccountEvent(
                account_id=historical_account.id,
                event_type="became_401",
                event_time=base_time - timedelta(minutes=5),
                related_snapshot_id=historical_snapshot.id,
                previous_snapshot_id=historical_snapshot.id,
                from_status_code=200,
                to_status_code=401,
                from_is_401=False,
                to_is_401=True,
                from_disabled=False,
                to_disabled=False,
                created_at=base_time - timedelta(minutes=5),
            )
        )
        db.commit()

    response = asyncio.run(_request("GET", "/api/v1/research/overview?window_days=7"))

    assert response.status_code == 200
    group_breakdown = response.json()["current_signal_baseline"]["current_signal_group_breakdown"]
    assert [item["label"] for item in group_breakdown] == [
        "openai / chatgpt",
        "azure / chatgpt",
    ]
    assert group_breakdown[0]["historical_like_accounts"] == 1
    assert group_breakdown[0]["historical_like_rate"] == 100.0
    assert group_breakdown[0]["top_historical_gap_bucket"] == "lt_15m"
    assert group_breakdown[0]["top_historical_gap_label"] == "15 分钟内"
    assert group_breakdown[0]["top_historical_gap_count"] == 1
    assert group_breakdown[0]["top_signal_pattern_key"] == "weekly_ge_90|limit_reached|allowed_false|status_message_present"
    assert [item["account_name"] for item in group_breakdown[0]["top_historical_like_samples"]] == [
        "Current-OpenAI-Exact",
    ]
    assert group_breakdown[1]["historical_like_accounts"] == 0
    assert group_breakdown[1]["historical_like_rate"] == 0.0
    assert group_breakdown[1]["top_historical_gap_bucket"] is None
    assert group_breakdown[1]["top_historical_gap_label"] is None
    assert group_breakdown[1]["top_historical_gap_count"] == 0
    assert group_breakdown[1]["top_signal_pattern_key"] in {"remaining_empty", "short_ge_90"}
    assert group_breakdown[1]["top_historical_like_samples"] == []

    app.dependency_overrides.clear()


def test_research_overview_api_prioritizes_groups_with_fresher_historical_evidence_on_tie() -> None:
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
            scan_started_at=base_time - timedelta(hours=1),
            scan_finished_at=base_time - timedelta(minutes=55),
            total_accounts=4,
            eligible_accounts=4,
            scanned_accounts=4,
            success_accounts=4,
            failed_accounts=0,
            new_401_events=2,
        )
        db.add(scan_job)
        db.flush()

        historical_fresh = Account(
            source_id=source.id,
            auth_index="historical-fresh",
            name="Historical-Fresh",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time - timedelta(minutes=5),
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time - timedelta(minutes=5),
        )
        historical_stale = Account(
            source_id=source.id,
            auth_index="historical-stale",
            name="Historical-Stale",
            provider="azure",
            account_type="chatgpt",
            disabled=False,
            current_is_401=True,
            current_status_code=401,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=2),
            last_seen_at=base_time,
        )
        current_fresh = Account(
            source_id=source.id,
            auth_index="current-fresh",
            name="Current-Fresh",
            provider="openai",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_weekly_used_percent=Decimal("95.00"),
            current_limit_reached=True,
            current_allowed=False,
            status_message="fresh signal",
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=1),
            last_seen_at=base_time,
        )
        current_stale = Account(
            source_id=source.id,
            auth_index="current-stale",
            name="Current-Stale",
            provider="azure",
            account_type="chatgpt",
            disabled=False,
            current_is_401=False,
            current_status_code=200,
            current_short_used_percent=Decimal("95.00"),
            current_limit_reached=True,
            current_allowed=False,
            current_last_checked_at=base_time,
            first_seen_at=base_time - timedelta(days=1),
            last_seen_at=base_time,
        )
        db.add_all([historical_fresh, historical_stale, current_fresh, current_stale])
        db.flush()

        historical_fresh_snapshot = AccountSnapshot(
            account_id=historical_fresh.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(minutes=10),
            created_at=base_time - timedelta(minutes=10),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            weekly_used_percent=Decimal("95.00"),
            limit_reached=True,
            allowed=False,
            status_message="fresh signal",
        )
        historical_stale_snapshot = AccountSnapshot(
            account_id=historical_stale.id,
            scan_job_id=scan_job.id,
            checked_at=base_time - timedelta(hours=8),
            created_at=base_time - timedelta(hours=8),
            snapshot_status="success",
            probe_status_code=200,
            is_401=False,
            short_used_percent=Decimal("95.00"),
            limit_reached=True,
            allowed=False,
        )
        db.add_all([historical_fresh_snapshot, historical_stale_snapshot])
        db.flush()

        db.add_all(
            [
                AccountEvent(
                    account_id=historical_fresh.id,
                    event_type="became_401",
                    event_time=base_time - timedelta(minutes=5),
                    related_snapshot_id=historical_fresh_snapshot.id,
                    previous_snapshot_id=historical_fresh_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time - timedelta(minutes=5),
                ),
                AccountEvent(
                    account_id=historical_stale.id,
                    event_type="became_401",
                    event_time=base_time,
                    related_snapshot_id=historical_stale_snapshot.id,
                    previous_snapshot_id=historical_stale_snapshot.id,
                    from_status_code=200,
                    to_status_code=401,
                    from_is_401=False,
                    to_is_401=True,
                    from_disabled=False,
                    to_disabled=False,
                    created_at=base_time,
                ),
            ]
        )
        db.commit()

    response = asyncio.run(_request("GET", "/api/v1/research/overview?window_days=7"))

    assert response.status_code == 200
    group_breakdown = response.json()["current_signal_baseline"]["current_signal_group_breakdown"]
    assert [item["label"] for item in group_breakdown] == [
        "openai / chatgpt",
        "azure / chatgpt",
    ]
    assert group_breakdown[0]["top_historical_gap_bucket"] == "lt_15m"
    assert group_breakdown[0]["top_historical_gap_label"] == "15 分钟内"
    assert group_breakdown[0]["top_historical_gap_count"] == 1
    assert group_breakdown[1]["top_historical_gap_bucket"] == "6h_24h"
    assert group_breakdown[1]["top_historical_gap_label"] == "6-24 小时"
    assert group_breakdown[1]["top_historical_gap_count"] == 1

    app.dependency_overrides.clear()
