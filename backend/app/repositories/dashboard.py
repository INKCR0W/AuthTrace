from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.account_event import AccountEvent
from app.models.scan_job import ScanJob


@dataclass(slots=True)
class OverviewTrendPoint:
    bucket_start: datetime
    became_401_count: int


@dataclass(slots=True)
class OverviewStats:
    total_accounts: int
    active_accounts: int
    disabled_accounts: int
    deleted_accounts: int
    current_401_accounts: int
    current_invalid_quota_accounts: int
    new_401_events_last_24h: int
    new_quota_events_last_24h: int
    recent_401_trend: list[OverviewTrendPoint]
    latest_scan_job: ScanJob | None


def get_overview_stats(db: Session) -> OverviewStats:
    total_accounts = _count_accounts(db)
    active_accounts = _count_accounts(db, Account.source_deleted_at.is_(None), Account.disabled.is_(False))
    disabled_accounts = _count_accounts(db, Account.source_deleted_at.is_(None), Account.disabled.is_(True))
    deleted_accounts = _count_accounts(db, Account.source_deleted_at.is_not(None))
    current_401_accounts = _count_accounts(
        db,
        Account.source_deleted_at.is_(None),
        Account.current_is_401.is_(True),
    )
    current_invalid_quota_accounts = _count_accounts(
        db,
        Account.source_deleted_at.is_(None),
        Account.current_invalid_quota.is_(True),
    )

    now = datetime.now(timezone.utc)
    current_bucket = now.replace(minute=0, second=0, microsecond=0)
    trend_start = current_bucket - timedelta(hours=23)
    trend_end = current_bucket + timedelta(hours=1)
    last_24h_start = now - timedelta(hours=24)

    recent_401_event_times = list(
        db.scalars(
            select(AccountEvent.event_time).where(
                AccountEvent.event_type == "became_401",
                AccountEvent.event_time >= trend_start,
                AccountEvent.event_time < trend_end,
            )
        ).all()
    )
    new_401_events_last_24h = int(
        db.scalar(
            select(func.count(AccountEvent.id)).where(
                AccountEvent.event_type == "became_401",
                AccountEvent.event_time >= last_24h_start,
            )
        )
        or 0
    )
    new_quota_events_last_24h = int(
        db.scalar(
            select(func.count(AccountEvent.id)).where(
                AccountEvent.event_type == "quota_exhausted",
                AccountEvent.event_time >= last_24h_start,
            )
        )
        or 0
    )

    latest_scan_job = db.scalar(select(ScanJob).order_by(ScanJob.scan_started_at.desc(), ScanJob.id.desc()).limit(1))

    return OverviewStats(
        total_accounts=total_accounts,
        active_accounts=active_accounts,
        disabled_accounts=disabled_accounts,
        deleted_accounts=deleted_accounts,
        current_401_accounts=current_401_accounts,
        current_invalid_quota_accounts=current_invalid_quota_accounts,
        new_401_events_last_24h=new_401_events_last_24h,
        new_quota_events_last_24h=new_quota_events_last_24h,
        recent_401_trend=_build_hourly_trend(window_start=trend_start, points=recent_401_event_times),
        latest_scan_job=latest_scan_job,
    )


def _count_accounts(db: Session, *conditions: object) -> int:
    statement = select(func.count(Account.id))
    for condition in conditions:
        statement = statement.where(condition)
    return int(db.scalar(statement) or 0)


def _build_hourly_trend(
    *,
    window_start: datetime,
    points: list[datetime],
) -> list[OverviewTrendPoint]:
    counter = Counter(point.replace(minute=0, second=0, microsecond=0) for point in points)
    return [
        OverviewTrendPoint(
            bucket_start=window_start + timedelta(hours=offset),
            became_401_count=counter.get(window_start + timedelta(hours=offset), 0),
        )
        for offset in range(24)
    ]
