from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.account_event import AccountEvent
from app.models.scan_job import ScanJob


@dataclass(slots=True)
class OverviewTrendPoint:
    bucket_start: datetime
    became_401_count: int


@dataclass(slots=True)
class DimensionBreakdownItem:
    value: str | None
    label: str
    total_accounts: int
    active_accounts: int
    disabled_accounts: int
    current_401_accounts: int
    current_invalid_quota_accounts: int
    became_401_events_last_24h: int
    current_401_rate: float
    current_invalid_quota_rate: float


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
    provider_breakdown: list[DimensionBreakdownItem]
    account_type_breakdown: list[DimensionBreakdownItem]
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
        provider_breakdown=_build_dimension_breakdown(
            db,
            dimension_column=Account.provider,
            last_24h_start=last_24h_start,
        ),
        account_type_breakdown=_build_dimension_breakdown(
            db,
            dimension_column=Account.account_type,
            last_24h_start=last_24h_start,
        ),
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


def _build_dimension_breakdown(
    db: Session,
    *,
    dimension_column: object,
    last_24h_start: datetime,
) -> list[DimensionBreakdownItem]:
    group_value = dimension_column.label("group_value")

    account_rows = db.execute(
        select(
            group_value,
            func.count(Account.id).label("total_accounts"),
            func.sum(case((Account.disabled.is_(False), 1), else_=0)).label("active_accounts"),
            func.sum(case((Account.disabled.is_(True), 1), else_=0)).label("disabled_accounts"),
            func.sum(case((Account.current_is_401.is_(True), 1), else_=0)).label("current_401_accounts"),
            func.sum(
                case((Account.current_invalid_quota.is_(True), 1), else_=0)
            ).label("current_invalid_quota_accounts"),
        )
        .where(Account.source_deleted_at.is_(None))
        .group_by(dimension_column)
    ).all()

    event_rows = db.execute(
        select(
            group_value,
            func.count(AccountEvent.id).label("became_401_events_last_24h"),
        )
        .select_from(AccountEvent)
        .join(Account, Account.id == AccountEvent.account_id)
        .where(
            Account.source_deleted_at.is_(None),
            AccountEvent.event_type == "became_401",
            AccountEvent.event_time >= last_24h_start,
        )
        .group_by(dimension_column)
    ).all()

    event_counts_by_value = {
        row.group_value: int(row.became_401_events_last_24h or 0)
        for row in event_rows
    }

    items = [
        DimensionBreakdownItem(
            value=str(row.group_value) if row.group_value is not None else None,
            label=str(row.group_value) if row.group_value is not None else "未标记",
            total_accounts=int(row.total_accounts or 0),
            active_accounts=int(row.active_accounts or 0),
            disabled_accounts=int(row.disabled_accounts or 0),
            current_401_accounts=int(row.current_401_accounts or 0),
            current_invalid_quota_accounts=int(row.current_invalid_quota_accounts or 0),
            became_401_events_last_24h=event_counts_by_value.get(row.group_value, 0),
            current_401_rate=_to_rate_percent(
                numerator=int(row.current_401_accounts or 0),
                denominator=int(row.total_accounts or 0),
            ),
            current_invalid_quota_rate=_to_rate_percent(
                numerator=int(row.current_invalid_quota_accounts or 0),
                denominator=int(row.total_accounts or 0),
            ),
        )
        for row in account_rows
    ]
    return sorted(
        items,
        key=lambda item: (
            -item.current_401_accounts,
            -item.became_401_events_last_24h,
            -item.current_invalid_quota_accounts,
            -item.total_accounts,
            item.label,
        ),
    )


def _to_rate_percent(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)
