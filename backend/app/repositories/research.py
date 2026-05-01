from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.models.account import Account
from app.models.account_event import AccountEvent
from app.models.account_snapshot import AccountSnapshot


@dataclass(slots=True)
class ResearchOverviewSummary:
    active_accounts: int
    current_401_accounts: int
    current_401_rate: float
    became_401_events: int
    affected_accounts: int
    affected_provider_groups: int
    sampled_previous_snapshots: int


@dataclass(slots=True)
class ResearchCombinationBreakdownItem:
    label: str
    provider: str | None
    account_type: str | None
    total_accounts: int
    current_401_accounts: int
    current_401_rate: float
    became_401_events: int
    affected_accounts: int
    last_became_401_at: datetime | None


@dataclass(slots=True)
class ResearchHourlyDistributionPoint:
    hour_of_day: int
    label: str
    became_401_count: int


@dataclass(slots=True)
class ResearchBucketCount:
    key: str
    label: str
    count: int


@dataclass(slots=True)
class ResearchPre401Insights:
    sampled_events: int
    events_with_previous_snapshot: int
    weekly_used_percent_bands: list[ResearchBucketCount]
    short_used_percent_bands: list[ResearchBucketCount]
    signal_breakdown: list[ResearchBucketCount]
    top_status_messages: list[ResearchBucketCount]


@dataclass(slots=True)
class ResearchEventSample:
    event_id: int
    account_id: int
    account_name: str
    provider: str | None
    account_type: str | None
    event_time: datetime
    current_is_401: bool
    previous_snapshot_id: int | None
    previous_checked_at: datetime | None
    previous_weekly_used_percent: Decimal | None
    previous_short_used_percent: Decimal | None
    previous_remaining: Decimal | None
    previous_limit_reached: bool | None
    previous_allowed: bool | None
    previous_status_message: str | None


@dataclass(slots=True)
class ResearchCurrentSignalSample:
    account_id: int
    account_name: str
    provider: str | None
    account_type: str | None
    current_last_checked_at: datetime | None
    current_weekly_used_percent: Decimal | None
    current_short_used_percent: Decimal | None
    current_remaining: Decimal | None
    current_limit_reached: bool | None
    current_allowed: bool | None
    status_message_excerpt: str | None
    signal_labels: list[str]


@dataclass(slots=True)
class ResearchCurrentSignalBaseline:
    observed_accounts: int
    signal_accounts: int
    signal_breakdown: list[ResearchBucketCount]
    recent_samples: list[ResearchCurrentSignalSample]


@dataclass(slots=True)
class ResearchOverview:
    window_days: int
    summary: ResearchOverviewSummary
    provider_account_type_breakdown: list[ResearchCombinationBreakdownItem]
    event_hour_distribution: list[ResearchHourlyDistributionPoint]
    pre_401_insights: ResearchPre401Insights
    recent_event_samples: list[ResearchEventSample]
    current_signal_baseline: ResearchCurrentSignalBaseline


@dataclass(slots=True)
class ResearchOverviewFilters:
    provider: str | None = None
    account_type: str | None = None


def get_research_overview(
    db: Session,
    *,
    window_days: int = 7,
    provider: str | None = None,
    account_type: str | None = None,
) -> ResearchOverview:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=window_days)
    filters = ResearchOverviewFilters(provider=provider, account_type=account_type)
    account_scope_conditions = _build_account_scope_conditions(filters)

    previous_snapshot = aliased(AccountSnapshot)
    event_rows = db.execute(
        select(AccountEvent, Account, previous_snapshot)
        .join(Account, Account.id == AccountEvent.account_id)
        .outerjoin(previous_snapshot, previous_snapshot.id == AccountEvent.previous_snapshot_id)
        .where(
            *account_scope_conditions,
            AccountEvent.event_type == "became_401",
            AccountEvent.event_time >= window_start,
        )
    ).all()

    active_accounts = int(
        db.scalar(
            select(func.count(Account.id)).where(
                *account_scope_conditions,
                Account.disabled.is_(False),
            )
        )
        or 0
    )
    current_population_accounts = int(
        db.scalar(select(func.count(Account.id)).where(*account_scope_conditions)) or 0
    )
    current_401_accounts = int(
        db.scalar(
            select(func.count(Account.id)).where(
                *account_scope_conditions,
                Account.current_is_401.is_(True),
            )
        )
        or 0
    )

    return ResearchOverview(
        window_days=window_days,
        summary=ResearchOverviewSummary(
            active_accounts=active_accounts,
            current_401_accounts=current_401_accounts,
            current_401_rate=_to_rate_percent(
                numerator=current_401_accounts,
                denominator=current_population_accounts,
            ),
            became_401_events=len(event_rows),
            affected_accounts=len({event.account_id for event, _, _ in event_rows}),
            affected_provider_groups=len(
                {
                    (
                        account.provider or "未标记 provider",
                        account.account_type or "未标记类型",
                    )
                    for _, account, _ in event_rows
                }
            ),
            sampled_previous_snapshots=sum(1 for _, _, snapshot in event_rows if snapshot is not None),
        ),
        provider_account_type_breakdown=_build_provider_account_type_breakdown(
            db,
            window_start=window_start,
            filters=filters,
        ),
        event_hour_distribution=_build_event_hour_distribution(event_rows),
        pre_401_insights=_build_pre_401_insights(event_rows),
        recent_event_samples=_build_recent_event_samples(event_rows),
        current_signal_baseline=_build_current_signal_baseline(db, filters=filters),
    )


def _build_provider_account_type_breakdown(
    db: Session,
    *,
    window_start: datetime,
    filters: ResearchOverviewFilters,
) -> list[ResearchCombinationBreakdownItem]:
    account_scope_conditions = _build_account_scope_conditions(filters)
    account_rows = db.execute(
        select(
            Account.provider.label("provider"),
            Account.account_type.label("account_type"),
            func.count(Account.id).label("total_accounts"),
            func.sum(case((Account.current_is_401.is_(True), 1), else_=0)).label("current_401_accounts"),
        )
        .where(*account_scope_conditions)
        .group_by(Account.provider, Account.account_type)
    ).all()

    event_rows = db.execute(
        select(
            Account.provider.label("provider"),
            Account.account_type.label("account_type"),
            func.count(AccountEvent.id).label("became_401_events"),
            func.count(func.distinct(AccountEvent.account_id)).label("affected_accounts"),
            func.max(AccountEvent.event_time).label("last_became_401_at"),
        )
        .select_from(AccountEvent)
        .join(Account, Account.id == AccountEvent.account_id)
        .where(
            *account_scope_conditions,
            AccountEvent.event_type == "became_401",
            AccountEvent.event_time >= window_start,
        )
        .group_by(Account.provider, Account.account_type)
    ).all()

    event_map = {
        (row.provider, row.account_type): {
            "became_401_events": int(row.became_401_events or 0),
            "affected_accounts": int(row.affected_accounts or 0),
            "last_became_401_at": _ensure_utc(row.last_became_401_at) if row.last_became_401_at else None,
        }
        for row in event_rows
    }

    items = [
        ResearchCombinationBreakdownItem(
            label=_build_combo_label(provider=row.provider, account_type=row.account_type),
            provider=row.provider,
            account_type=row.account_type,
            total_accounts=int(row.total_accounts or 0),
            current_401_accounts=int(row.current_401_accounts or 0),
            current_401_rate=_to_rate_percent(
                numerator=int(row.current_401_accounts or 0),
                denominator=int(row.total_accounts or 0),
            ),
            became_401_events=event_map.get((row.provider, row.account_type), {}).get("became_401_events", 0),
            affected_accounts=event_map.get((row.provider, row.account_type), {}).get("affected_accounts", 0),
            last_became_401_at=event_map.get((row.provider, row.account_type), {}).get("last_became_401_at"),
        )
        for row in account_rows
    ]
    return sorted(
        items,
        key=lambda item: (
            -item.became_401_events,
            -item.current_401_accounts,
            -item.total_accounts,
            item.label,
        ),
    )


def _build_event_hour_distribution(
    event_rows: list[tuple[AccountEvent, Account, AccountSnapshot | None]],
) -> list[ResearchHourlyDistributionPoint]:
    hour_counter = Counter(_ensure_utc(event.event_time).hour for event, _, _ in event_rows)
    return [
        ResearchHourlyDistributionPoint(
            hour_of_day=hour,
            label=f"{hour:02d}:00",
            became_401_count=hour_counter.get(hour, 0),
        )
        for hour in range(24)
    ]


def _build_pre_401_insights(
    event_rows: list[tuple[AccountEvent, Account, AccountSnapshot | None]],
) -> ResearchPre401Insights:
    previous_snapshots = [snapshot for _, _, snapshot in event_rows if snapshot is not None]
    weekly_counter = Counter(_bucket_percent(snapshot.weekly_used_percent) for snapshot in previous_snapshots)
    short_counter = Counter(_bucket_percent(snapshot.short_used_percent) for snapshot in previous_snapshots)
    signal_counter = Counter[str]()
    status_counter = Counter[str]()

    for snapshot in previous_snapshots:
        if _decimal_gte(snapshot.weekly_used_percent, Decimal("90")):
            signal_counter["weekly_ge_90"] += 1
        if _decimal_gte(snapshot.short_used_percent, Decimal("90")):
            signal_counter["short_ge_90"] += 1
        if snapshot.limit_reached is True:
            signal_counter["limit_reached"] += 1
        if snapshot.allowed is False:
            signal_counter["allowed_false"] += 1
        if snapshot.remaining is not None and snapshot.remaining <= 0:
            signal_counter["remaining_empty"] += 1
        if (snapshot.status_message or "").strip():
            signal_counter["status_message_present"] += 1
            status_counter[snapshot.status_message.strip()] += 1

    return ResearchPre401Insights(
        sampled_events=len(event_rows),
        events_with_previous_snapshot=len(previous_snapshots),
        weekly_used_percent_bands=_build_percent_band_counts(weekly_counter),
        short_used_percent_bands=_build_percent_band_counts(short_counter),
        signal_breakdown=_build_signal_breakdown(signal_counter),
        top_status_messages=_build_top_status_messages(status_counter),
    )


def _build_recent_event_samples(
    event_rows: list[tuple[AccountEvent, Account, AccountSnapshot | None]],
) -> list[ResearchEventSample]:
    samples = [
        ResearchEventSample(
            event_id=event.id,
            account_id=account.id,
            account_name=account.name,
            provider=account.provider,
            account_type=account.account_type,
            event_time=_ensure_utc(event.event_time),
            current_is_401=account.current_is_401,
            previous_snapshot_id=previous_snapshot.id if previous_snapshot is not None else None,
            previous_checked_at=(
                _ensure_utc(previous_snapshot.checked_at)
                if previous_snapshot is not None
                else None
            ),
            previous_weekly_used_percent=(
                previous_snapshot.weekly_used_percent
                if previous_snapshot is not None
                else None
            ),
            previous_short_used_percent=(
                previous_snapshot.short_used_percent
                if previous_snapshot is not None
                else None
            ),
            previous_remaining=previous_snapshot.remaining if previous_snapshot is not None else None,
            previous_limit_reached=(
                previous_snapshot.limit_reached
                if previous_snapshot is not None
                else None
            ),
            previous_allowed=previous_snapshot.allowed if previous_snapshot is not None else None,
            previous_status_message=(
                previous_snapshot.status_message
                if previous_snapshot is not None
                else None
            ),
        )
        for event, account, previous_snapshot in event_rows
    ]
    return sorted(
        samples,
        key=lambda item: (item.event_time, item.event_id),
        reverse=True,
    )[:10]


def _build_current_signal_baseline(
    db: Session,
    *,
    filters: ResearchOverviewFilters,
) -> ResearchCurrentSignalBaseline:
    account_scope_conditions = _build_account_scope_conditions(filters)
    account_rows = list(
        db.scalars(
            select(Account).where(
                *account_scope_conditions,
                Account.disabled.is_(False),
                Account.current_is_401.is_(False),
            )
        )
    )

    signal_counter = Counter[str]()
    samples: list[ResearchCurrentSignalSample] = []

    for account in account_rows:
        signal_keys = _extract_account_signal_keys(account)
        if not signal_keys:
            continue

        signal_counter.update(signal_keys)
        samples.append(
            ResearchCurrentSignalSample(
                account_id=account.id,
                account_name=account.name,
                provider=account.provider,
                account_type=account.account_type,
                current_last_checked_at=(
                    _ensure_utc(account.current_last_checked_at)
                    if account.current_last_checked_at is not None
                    else None
                ),
                current_weekly_used_percent=account.current_weekly_used_percent,
                current_short_used_percent=account.current_short_used_percent,
                current_remaining=account.current_remaining,
                current_limit_reached=account.current_limit_reached,
                current_allowed=account.current_allowed,
                status_message_excerpt=_build_status_message_excerpt(account.status_message),
                signal_labels=[_SIGNAL_LABELS[key] for key in signal_keys],
            )
        )

    samples.sort(
        key=lambda item: (
            -len(item.signal_labels),
            -(item.current_weekly_used_percent or Decimal("-1")),
            -(item.current_short_used_percent or Decimal("-1")),
            -_datetime_to_timestamp(item.current_last_checked_at),
            item.account_name,
        )
    )

    return ResearchCurrentSignalBaseline(
        observed_accounts=len(account_rows),
        signal_accounts=len(samples),
        signal_breakdown=_build_signal_breakdown(signal_counter),
        recent_samples=samples[:10],
    )


def _build_percent_band_counts(counter: Counter[str]) -> list[ResearchBucketCount]:
    bands = [
        ("0_24", "0-24%", counter.get("0_24", 0)),
        ("25_49", "25-49%", counter.get("25_49", 0)),
        ("50_74", "50-74%", counter.get("50_74", 0)),
        ("75_89", "75-89%", counter.get("75_89", 0)),
        ("90_100", "90-100%", counter.get("90_100", 0)),
        ("missing", "未记录", counter.get("missing", 0)),
    ]
    return [ResearchBucketCount(key=key, label=label, count=count) for key, label, count in bands]


def _build_signal_breakdown(counter: Counter[str]) -> list[ResearchBucketCount]:
    items = [
        ResearchBucketCount(key=key, label=_SIGNAL_LABELS[key], count=count)
        for key, count in counter.items()
        if count > 0 and key in _SIGNAL_LABELS
    ]
    return sorted(items, key=lambda item: (-item.count, item.label))


def _build_top_status_messages(counter: Counter[str]) -> list[ResearchBucketCount]:
    items = [
        ResearchBucketCount(key=message, label=message, count=count)
        for message, count in counter.items()
    ]
    return sorted(items, key=lambda item: (-item.count, item.label))[:5]


_SIGNAL_LABELS = {
    "weekly_ge_90": "周额度 >= 90%",
    "short_ge_90": "短周期 >= 90%",
    "limit_reached": "limit_reached=true",
    "allowed_false": "allowed=false",
    "remaining_empty": "remaining <= 0",
    "status_message_present": "存在 status_message",
}


def _extract_account_signal_keys(account: Account) -> list[str]:
    signal_keys: list[str] = []

    if _decimal_gte(account.current_weekly_used_percent, Decimal("90")):
        signal_keys.append("weekly_ge_90")
    if _decimal_gte(account.current_short_used_percent, Decimal("90")):
        signal_keys.append("short_ge_90")
    if account.current_limit_reached is True:
        signal_keys.append("limit_reached")
    if account.current_allowed is False:
        signal_keys.append("allowed_false")
    if account.current_remaining is not None and account.current_remaining <= 0:
        signal_keys.append("remaining_empty")
    if (account.status_message or "").strip():
        signal_keys.append("status_message_present")

    return signal_keys


def _build_status_message_excerpt(value: str | None, *, limit: int = 120) -> str | None:
    if value is None:
        return None

    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _bucket_percent(value: Decimal | None) -> str:
    if value is None:
        return "missing"
    if value < 25:
        return "0_24"
    if value < 50:
        return "25_49"
    if value < 75:
        return "50_74"
    if value < 90:
        return "75_89"
    return "90_100"


def _build_combo_label(*, provider: str | None, account_type: str | None) -> str:
    provider_label = provider or "未标记 provider"
    account_type_label = account_type or "未标记类型"
    return f"{provider_label} / {account_type_label}"


def _build_account_scope_conditions(filters: ResearchOverviewFilters) -> list[object]:
    conditions: list[object] = [Account.source_deleted_at.is_(None)]

    if filters.provider:
        conditions.append(Account.provider == filters.provider)
    if filters.account_type:
        conditions.append(Account.account_type == filters.account_type)

    return conditions


def _decimal_gte(value: Decimal | None, threshold: Decimal) -> bool:
    if value is None:
        return False
    return value >= threshold


def _to_rate_percent(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _datetime_to_timestamp(value: datetime | None) -> float:
    if value is None:
        return float("-inf")
    return value.timestamp()
