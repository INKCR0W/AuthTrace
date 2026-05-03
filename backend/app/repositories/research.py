from __future__ import annotations

import json
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
class ResearchSignalComparisonItem:
    key: str
    label: str
    pre_401_count: int
    pre_401_rate: float
    current_count: int
    current_rate: float
    rate_gap: float


@dataclass(slots=True)
class ResearchSignalPatternComparisonItem:
    key: str
    label: str
    pre_401_count: int
    pre_401_rate: float
    current_count: int
    current_rate: float
    rate_gap: float


@dataclass(slots=True)
class ResearchPre401Insights:
    sampled_events: int
    events_with_previous_snapshot: int
    previous_to_event_gap_bands: list[ResearchBucketCount]
    weekly_used_percent_bands: list[ResearchBucketCount]
    short_used_percent_bands: list[ResearchBucketCount]
    signal_breakdown: list[ResearchBucketCount]
    signal_pattern_breakdown: list[ResearchBucketCount]
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
    previous_to_event_gap_minutes: int | None
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
    consecutive_signal_snapshots: int
    signal_started_at: datetime | None
    historical_match_level: str
    historical_match_label: str
    historical_match_rate: float
    historical_best_pattern: str | None
    historical_overlap_signal_labels: list[str]
    historical_current_only_signal_labels: list[str]
    historical_pattern_only_signal_labels: list[str]
    historical_match_event_id: int | None
    historical_match_event_account_id: int | None
    historical_match_event_account_name: str | None
    historical_match_event_time: datetime | None
    historical_match_gap_bucket: str | None
    historical_match_gap_label: str | None
    historical_match_gap_minutes: int | None
    historical_like_event_count: int


@dataclass(slots=True)
class ResearchCurrentSignalGroupSample:
    account_id: int
    account_name: str
    current_last_checked_at: datetime | None
    signal_labels: list[str]
    consecutive_signal_snapshots: int
    historical_match_level: str
    historical_match_label: str
    historical_match_rate: float
    historical_best_pattern: str | None
    historical_overlap_signal_labels: list[str]
    historical_current_only_signal_labels: list[str]
    historical_pattern_only_signal_labels: list[str]
    historical_match_event_id: int | None
    historical_match_event_account_id: int | None
    historical_match_event_account_name: str | None
    historical_match_event_time: datetime | None
    historical_match_gap_bucket: str | None
    historical_match_gap_label: str | None
    historical_match_gap_minutes: int | None
    historical_like_event_count: int


@dataclass(slots=True)
class ResearchCurrentSignalGroupBreakdownItem:
    label: str
    provider: str | None
    account_type: str | None
    observed_accounts: int
    signal_accounts: int
    signal_rate: float
    multi_round_signal_accounts: int
    historical_like_accounts: int
    historical_like_rate: float
    top_historical_gap_bucket: str | None
    top_historical_gap_label: str | None
    top_historical_gap_count: int
    top_signal_pattern_key: str | None
    top_signal_pattern: str | None
    top_historical_like_samples: list[ResearchCurrentSignalGroupSample]


@dataclass(slots=True)
class ResearchHistoricalReplayBreakdownItem:
    event_id: int
    event_account_id: int
    event_account_name: str
    event_time: datetime
    historical_best_pattern: str
    historical_gap_bucket: str
    historical_gap_label: str
    historical_gap_minutes: int
    matched_current_accounts: int
    matched_current_rate: float
    exact_match_accounts: int
    covered_match_accounts: int
    partial_overlap_accounts: int


@dataclass(slots=True)
class ResearchCurrentSignalBaseline:
    observed_accounts: int
    signal_accounts: int
    signal_breakdown: list[ResearchBucketCount]
    signal_pattern_breakdown: list[ResearchBucketCount]
    signal_streak_breakdown: list[ResearchBucketCount]
    historical_match_breakdown: list[ResearchBucketCount]
    historical_like_event_count_breakdown: list[ResearchBucketCount]
    historical_match_gap_breakdown: list[ResearchBucketCount]
    historical_replay_breakdown: list[ResearchHistoricalReplayBreakdownItem]
    current_signal_group_breakdown: list[ResearchCurrentSignalGroupBreakdownItem]
    top_status_messages: list[ResearchBucketCount]
    recent_samples: list[ResearchCurrentSignalSample]


@dataclass(slots=True)
class ResearchOverview:
    window_days: int
    summary: ResearchOverviewSummary
    provider_account_type_breakdown: list[ResearchCombinationBreakdownItem]
    event_hour_distribution: list[ResearchHourlyDistributionPoint]
    signal_comparison: list[ResearchSignalComparisonItem]
    signal_pattern_comparison: list[ResearchSignalPatternComparisonItem]
    pre_401_insights: ResearchPre401Insights
    recent_event_samples: list[ResearchEventSample]
    current_signal_baseline: ResearchCurrentSignalBaseline


@dataclass(slots=True)
class ResearchOverviewFilters:
    provider: str | None = None
    account_type: str | None = None
    current_signal_key: str | None = None
    current_status_message: str | None = None
    current_signal_pattern_key: str | None = None
    pre_401_signal_key: str | None = None
    pre_401_status_message: str | None = None
    pre_401_signal_pattern_key: str | None = None
    pre_401_gap_bucket: str | None = None
    current_match_level: str | None = None
    current_signal_min_streak: int | None = None
    current_historical_like_bucket: str | None = None
    current_historical_gap_bucket: str | None = None
    current_historical_event_id: int | None = None


def get_research_overview(
    db: Session,
    *,
    window_days: int = 7,
    provider: str | None = None,
    account_type: str | None = None,
    current_signal_key: str | None = None,
    current_status_message: str | None = None,
    current_signal_pattern_key: str | None = None,
    pre_401_signal_key: str | None = None,
    pre_401_status_message: str | None = None,
    pre_401_signal_pattern_key: str | None = None,
    pre_401_gap_bucket: str | None = None,
    current_match_level: str | None = None,
    current_signal_min_streak: int | None = None,
    current_historical_like_bucket: str | None = None,
    current_historical_gap_bucket: str | None = None,
    current_historical_event_id: int | None = None,
) -> ResearchOverview:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=window_days)
    filters = ResearchOverviewFilters(
        provider=provider,
        account_type=account_type,
        current_signal_key=current_signal_key,
        current_status_message=_normalize_status_message_filter(current_status_message),
        current_signal_pattern_key=current_signal_pattern_key,
        pre_401_signal_key=pre_401_signal_key,
        pre_401_status_message=_normalize_status_message_filter(pre_401_status_message),
        pre_401_signal_pattern_key=pre_401_signal_pattern_key,
        pre_401_gap_bucket=pre_401_gap_bucket,
        current_match_level=current_match_level,
        current_signal_min_streak=current_signal_min_streak,
        current_historical_like_bucket=current_historical_like_bucket,
        current_historical_gap_bucket=current_historical_gap_bucket,
        current_historical_event_id=current_historical_event_id,
    )
    scope_filters = ResearchOverviewFilters(
        provider=provider,
        account_type=account_type,
    )
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
    pre_401_event_rows = _filter_event_rows_by_previous_signal(
        event_rows,
        signal_key=filters.pre_401_signal_key,
        status_message=filters.pre_401_status_message,
        pattern_key=filters.pre_401_signal_pattern_key,
        gap_bucket=filters.pre_401_gap_bucket,
    )

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
        signal_comparison=_build_signal_comparison(
            db,
            event_rows=event_rows,
            filters=scope_filters,
        ),
        signal_pattern_comparison=_build_signal_pattern_comparison(
            db,
            event_rows=event_rows,
            filters=scope_filters,
        ),
        pre_401_insights=_build_pre_401_insights(pre_401_event_rows),
        recent_event_samples=_build_recent_event_samples(pre_401_event_rows),
        current_signal_baseline=_build_current_signal_baseline(
            db,
            filters=filters,
            historical_event_rows=event_rows,
        ),
    )


def _filter_event_rows_by_previous_signal(
    event_rows: list[tuple[AccountEvent, Account, AccountSnapshot | None]],
    *,
    signal_key: str | None,
    status_message: str | None,
    pattern_key: str | None,
    gap_bucket: str | None,
) -> list[tuple[AccountEvent, Account, AccountSnapshot | None]]:
    if signal_key is None and status_message is None and pattern_key is None and gap_bucket is None:
        return event_rows

    filtered_rows: list[tuple[AccountEvent, Account, AccountSnapshot | None]] = []
    for row in event_rows:
        previous_snapshot = row[2]
        if previous_snapshot is None:
            continue
        if gap_bucket is not None:
            previous_gap_bucket = _bucket_previous_gap(
                event_time=row[0].event_time,
                previous_checked_at=previous_snapshot.checked_at,
            )
            if previous_gap_bucket != gap_bucket:
                continue
        if (
            status_message is not None
            and _build_status_message_excerpt(previous_snapshot.status_message) != status_message
        ):
            continue
        signal_keys = _extract_snapshot_signal_keys(previous_snapshot)
        if signal_key is not None and signal_key not in signal_keys:
            continue
        if pattern_key is not None and "|".join(signal_keys) != pattern_key:
            continue
        filtered_rows.append(row)

    return filtered_rows


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
    previous_gap_counter = Counter[str]()
    weekly_counter = Counter(_bucket_percent(snapshot.weekly_used_percent) for snapshot in previous_snapshots)
    short_counter = Counter(_bucket_percent(snapshot.short_used_percent) for snapshot in previous_snapshots)
    signal_counter = Counter[str]()
    pattern_counter = Counter[str]()
    status_counter = Counter[str]()

    for event, _, snapshot in event_rows:
        if snapshot is None:
            continue
        previous_gap_counter[_bucket_previous_gap(event_time=event.event_time, previous_checked_at=snapshot.checked_at)] += 1
        signal_keys = _extract_snapshot_signal_keys(snapshot)
        signal_counter.update(signal_keys)
        if signal_keys:
            pattern_counter["|".join(signal_keys)] += 1
        status_message_excerpt = _build_status_message_excerpt(snapshot.status_message)
        if status_message_excerpt:
            status_counter[status_message_excerpt] += 1

    return ResearchPre401Insights(
        sampled_events=len(event_rows),
        events_with_previous_snapshot=len(previous_snapshots),
        previous_to_event_gap_bands=_build_previous_gap_band_counts(previous_gap_counter),
        weekly_used_percent_bands=_build_percent_band_counts(weekly_counter),
        short_used_percent_bands=_build_percent_band_counts(short_counter),
        signal_breakdown=_build_signal_breakdown(signal_counter),
        signal_pattern_breakdown=_build_signal_pattern_breakdown(pattern_counter),
        top_status_messages=_build_top_status_messages(status_counter),
    )


def _build_signal_comparison(
    db: Session,
    *,
    event_rows: list[tuple[AccountEvent, Account, AccountSnapshot | None]],
    filters: ResearchOverviewFilters,
) -> list[ResearchSignalComparisonItem]:
    previous_snapshots = [snapshot for _, _, snapshot in event_rows if snapshot is not None]
    if not previous_snapshots:
        return []

    pre_401_counter = Counter[str]()
    for snapshot in previous_snapshots:
        pre_401_counter.update(_extract_snapshot_signal_keys(snapshot))

    current_accounts = list(
        db.scalars(
            select(Account).where(
                *_build_account_scope_conditions(filters),
                Account.disabled.is_(False),
                Account.current_is_401.is_(False),
            )
        )
    )
    current_counter = Counter[str]()
    for account in current_accounts:
        current_counter.update(_extract_account_signal_keys(account))

    pre_401_denominator = len(previous_snapshots)
    current_denominator = len(current_accounts)
    items = [
        ResearchSignalComparisonItem(
            key=key,
            label=_SIGNAL_LABELS[key],
            pre_401_count=pre_401_counter.get(key, 0),
            pre_401_rate=_to_rate_percent(
                numerator=pre_401_counter.get(key, 0),
                denominator=pre_401_denominator,
            ),
            current_count=current_counter.get(key, 0),
            current_rate=_to_rate_percent(
                numerator=current_counter.get(key, 0),
                denominator=current_denominator,
            ),
            rate_gap=round(
                _to_rate_percent(
                    numerator=pre_401_counter.get(key, 0),
                    denominator=pre_401_denominator,
                )
                - _to_rate_percent(
                    numerator=current_counter.get(key, 0),
                    denominator=current_denominator,
                ),
                2,
            ),
        )
        for key in RESEARCH_SIGNAL_KEYS
    ]
    return sorted(
        items,
        key=lambda item: (
            -int(item.pre_401_count > 0 or item.current_count > 0),
            -item.rate_gap,
            -item.pre_401_count,
            -item.current_count,
            item.current_rate,
            item.label,
        ),
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
            previous_to_event_gap_minutes=(
                _build_gap_minutes(event_time=event.event_time, previous_checked_at=previous_snapshot.checked_at)
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
                _build_status_message_excerpt(previous_snapshot.status_message)
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


def _build_signal_pattern_comparison(
    db: Session,
    *,
    event_rows: list[tuple[AccountEvent, Account, AccountSnapshot | None]],
    filters: ResearchOverviewFilters,
) -> list[ResearchSignalPatternComparisonItem]:
    previous_snapshots = [snapshot for _, _, snapshot in event_rows if snapshot is not None]
    if not previous_snapshots:
        return []

    pre_401_counter = Counter[str]()
    for snapshot in previous_snapshots:
        signal_keys = _extract_snapshot_signal_keys(snapshot)
        if signal_keys:
            pre_401_counter["|".join(signal_keys)] += 1

    current_accounts = list(
        db.scalars(
            select(Account).where(
                *_build_account_scope_conditions(filters),
                Account.disabled.is_(False),
                Account.current_is_401.is_(False),
            )
        )
    )
    current_counter = Counter[str]()
    for account in current_accounts:
        signal_keys = _extract_account_signal_keys(account)
        if signal_keys:
            current_counter["|".join(signal_keys)] += 1

    pre_401_denominator = len(previous_snapshots)
    current_denominator = len(current_accounts)
    items = [
        ResearchSignalPatternComparisonItem(
            key=pattern_key,
            label=_build_signal_pattern_label(pattern_key),
            pre_401_count=pre_401_counter.get(pattern_key, 0),
            pre_401_rate=_to_rate_percent(
                numerator=pre_401_counter.get(pattern_key, 0),
                denominator=pre_401_denominator,
            ),
            current_count=current_counter.get(pattern_key, 0),
            current_rate=_to_rate_percent(
                numerator=current_counter.get(pattern_key, 0),
                denominator=current_denominator,
            ),
            rate_gap=round(
                _to_rate_percent(
                    numerator=pre_401_counter.get(pattern_key, 0),
                    denominator=pre_401_denominator,
                )
                - _to_rate_percent(
                    numerator=current_counter.get(pattern_key, 0),
                    denominator=current_denominator,
                ),
                2,
            ),
        )
        for pattern_key in set(pre_401_counter) | set(current_counter)
    ]
    return sorted(
        items,
        key=lambda item: (
            -int(item.pre_401_count > 0 or item.current_count > 0),
            -item.rate_gap,
            -item.pre_401_count,
            -item.current_count,
            item.label,
            item.key,
        ),
    )[:8]


def _build_current_signal_baseline(
    db: Session,
    *,
    filters: ResearchOverviewFilters,
    historical_event_rows: list[tuple[AccountEvent, Account, AccountSnapshot | None]],
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

    observed_group_counter = Counter(
        (account.provider, account.account_type) for account in account_rows
    )
    signal_counter = Counter[str]()
    pattern_counter = Counter[str]()
    streak_counter = Counter[str]()
    historical_match_counter = Counter[str]()
    historical_like_event_count_counter = Counter[str]()
    historical_match_gap_counter = Counter[str]()
    historical_replay_counter = Counter[int]()
    exact_replay_counter = Counter[int]()
    covered_replay_counter = Counter[int]()
    partial_replay_counter = Counter[int]()
    status_counter = Counter[str]()
    signal_group_counter = Counter[tuple[str | None, str | None]]()
    multi_round_group_counter = Counter[tuple[str | None, str | None]]()
    historical_like_group_counter = Counter[tuple[str | None, str | None]]()
    group_historical_gap_counter: dict[tuple[str | None, str | None], Counter[str]] = {}
    group_pattern_counter: dict[tuple[str | None, str | None], Counter[str]] = {}
    group_historical_like_samples: dict[
        tuple[str | None, str | None],
        list[ResearchCurrentSignalGroupSample],
    ] = {}
    historical_replay_meta_by_event_id: dict[int, _HistoricalReplayBreakdownMeta] = {}
    samples: list[ResearchCurrentSignalSample] = []
    signal_candidates: list[tuple[Account, list[str], str]] = []

    for account in account_rows:
        signal_keys = _extract_account_signal_keys(account)
        if not signal_keys:
            continue
        if filters.current_signal_key and filters.current_signal_key not in signal_keys:
            continue

        pattern_key = "|".join(signal_keys)
        if filters.current_signal_pattern_key and filters.current_signal_pattern_key != pattern_key:
            continue
        signal_candidates.append((account, signal_keys, pattern_key))

    snapshots_by_account_id = _load_success_snapshots_by_account_id(
        db,
        account_ids=[account.id for account, _, _ in signal_candidates],
    )
    historical_candidates = _build_historical_signal_candidates(historical_event_rows)

    for account, signal_keys, pattern_key in signal_candidates:
        status_message_excerpt = _build_status_message_excerpt(account.status_message)
        if (
            filters.current_status_message is not None
            and status_message_excerpt != filters.current_status_message
        ):
            continue
        group_key = (account.provider, account.account_type)
        consecutive_signal_snapshots, signal_started_at = _build_current_signal_streak(
            account=account,
            snapshots=snapshots_by_account_id.get(account.id, []),
        )
        historical_match = _evaluate_historical_signal_match(
            signal_keys=signal_keys,
            historical_candidates=historical_candidates,
        )
        if filters.current_match_level and historical_match.level != filters.current_match_level:
            continue
        if (
            filters.current_signal_min_streak is not None
            and consecutive_signal_snapshots < filters.current_signal_min_streak
        ):
            continue
        if (
            filters.current_historical_like_bucket is not None
            and _bucket_historical_like_event_count(historical_match.like_event_count)
            != filters.current_historical_like_bucket
        ):
            continue
        if (
            filters.current_historical_gap_bucket is not None
            and historical_match.best_gap_bucket != filters.current_historical_gap_bucket
        ):
            continue
        if (
            filters.current_historical_event_id is not None
            and historical_match.best_event_id != filters.current_historical_event_id
        ):
            continue
        signal_counter.update(signal_keys)
        pattern_counter[pattern_key] += 1
        signal_group_counter[group_key] += 1
        group_pattern_counter.setdefault(group_key, Counter())[pattern_key] += 1
        streak_counter[_bucket_signal_streak(consecutive_signal_snapshots)] += 1
        historical_match_counter[historical_match.level] += 1
        historical_like_bucket = _bucket_historical_like_event_count(
            historical_match.like_event_count
        )
        if historical_like_bucket is not None:
            historical_like_event_count_counter[historical_like_bucket] += 1
        if historical_match.best_gap_bucket is not None:
            historical_match_gap_counter[historical_match.best_gap_bucket] += 1
        if (
            historical_match.best_event_id is not None
            and historical_match.best_event_account_id is not None
            and historical_match.best_event_account_name is not None
            and historical_match.best_event_time is not None
            and historical_match.best_pattern_label is not None
            and historical_match.best_gap_bucket is not None
            and historical_match.best_gap_label is not None
            and historical_match.best_gap_minutes is not None
        ):
            historical_replay_counter[historical_match.best_event_id] += 1
            historical_replay_meta_by_event_id[historical_match.best_event_id] = _HistoricalReplayBreakdownMeta(
                event_id=historical_match.best_event_id,
                event_account_id=historical_match.best_event_account_id,
                event_account_name=historical_match.best_event_account_name,
                event_time=historical_match.best_event_time,
                historical_best_pattern=historical_match.best_pattern_label,
                historical_gap_bucket=historical_match.best_gap_bucket,
                historical_gap_label=historical_match.best_gap_label,
                historical_gap_minutes=historical_match.best_gap_minutes,
            )
            if historical_match.level == "exact_pattern":
                exact_replay_counter[historical_match.best_event_id] += 1
            elif historical_match.level == "covered_pattern":
                covered_replay_counter[historical_match.best_event_id] += 1
            elif historical_match.level == "partial_overlap":
                partial_replay_counter[historical_match.best_event_id] += 1
        if consecutive_signal_snapshots >= 2:
            multi_round_group_counter[group_key] += 1
        if historical_match.level in _HISTORICAL_LIKE_LEVELS:
            historical_like_group_counter[group_key] += 1
            if historical_match.best_gap_bucket is not None:
                group_historical_gap_counter.setdefault(group_key, Counter())[
                    historical_match.best_gap_bucket
                ] += 1
        status_message_bucket = status_message_excerpt
        if status_message_bucket:
            status_counter[status_message_bucket] += 1
        current_sample = ResearchCurrentSignalSample(
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
            status_message_excerpt=status_message_excerpt,
            signal_labels=[_SIGNAL_LABELS[key] for key in signal_keys],
            consecutive_signal_snapshots=consecutive_signal_snapshots,
            signal_started_at=signal_started_at,
            historical_match_level=historical_match.level,
            historical_match_label=_HISTORICAL_MATCH_LABELS[historical_match.level],
            historical_match_rate=historical_match.rate,
            historical_best_pattern=historical_match.best_pattern_label,
            historical_overlap_signal_labels=historical_match.overlap_signal_labels,
            historical_current_only_signal_labels=historical_match.current_only_signal_labels,
            historical_pattern_only_signal_labels=historical_match.historical_only_signal_labels,
            historical_match_event_id=historical_match.best_event_id,
            historical_match_event_account_id=historical_match.best_event_account_id,
            historical_match_event_account_name=historical_match.best_event_account_name,
            historical_match_event_time=historical_match.best_event_time,
            historical_match_gap_bucket=historical_match.best_gap_bucket,
            historical_match_gap_label=historical_match.best_gap_label,
            historical_match_gap_minutes=historical_match.best_gap_minutes,
            historical_like_event_count=historical_match.like_event_count,
        )
        samples.append(current_sample)
        if historical_match.level in _HISTORICAL_LIKE_LEVELS:
            group_historical_like_samples.setdefault(group_key, []).append(
                ResearchCurrentSignalGroupSample(
                    account_id=current_sample.account_id,
                    account_name=current_sample.account_name,
                    current_last_checked_at=current_sample.current_last_checked_at,
                    signal_labels=current_sample.signal_labels,
                    consecutive_signal_snapshots=current_sample.consecutive_signal_snapshots,
                    historical_match_level=current_sample.historical_match_level,
                    historical_match_label=current_sample.historical_match_label,
                    historical_match_rate=current_sample.historical_match_rate,
                    historical_best_pattern=current_sample.historical_best_pattern,
                    historical_overlap_signal_labels=current_sample.historical_overlap_signal_labels,
                    historical_current_only_signal_labels=current_sample.historical_current_only_signal_labels,
                    historical_pattern_only_signal_labels=current_sample.historical_pattern_only_signal_labels,
                    historical_match_event_id=current_sample.historical_match_event_id,
                    historical_match_event_account_id=current_sample.historical_match_event_account_id,
                    historical_match_event_account_name=current_sample.historical_match_event_account_name,
                    historical_match_event_time=current_sample.historical_match_event_time,
                    historical_match_gap_bucket=current_sample.historical_match_gap_bucket,
                    historical_match_gap_label=current_sample.historical_match_gap_label,
                    historical_match_gap_minutes=current_sample.historical_match_gap_minutes,
                    historical_like_event_count=current_sample.historical_like_event_count,
                )
            )

    samples.sort(
        key=lambda item: _build_current_signal_sort_key(
            historical_match_level=item.historical_match_level,
            historical_match_rate=item.historical_match_rate,
            consecutive_signal_snapshots=item.consecutive_signal_snapshots,
            signal_label_count=len(item.signal_labels),
            current_weekly_used_percent=item.current_weekly_used_percent,
            current_short_used_percent=item.current_short_used_percent,
            current_last_checked_at=item.current_last_checked_at,
            account_name=item.account_name,
        )
    )

    return ResearchCurrentSignalBaseline(
        observed_accounts=len(account_rows),
        signal_accounts=len(samples),
        signal_breakdown=_build_signal_breakdown(signal_counter),
        signal_pattern_breakdown=_build_signal_pattern_breakdown(pattern_counter),
        signal_streak_breakdown=_build_signal_streak_breakdown(streak_counter),
        historical_match_breakdown=_build_historical_match_breakdown(historical_match_counter),
        historical_like_event_count_breakdown=_build_historical_like_event_count_breakdown(
            historical_like_event_count_counter
        ),
        historical_match_gap_breakdown=_build_historical_match_gap_breakdown(historical_match_gap_counter),
        historical_replay_breakdown=_build_historical_replay_breakdown(
            replay_counter=historical_replay_counter,
            exact_counter=exact_replay_counter,
            covered_counter=covered_replay_counter,
            partial_counter=partial_replay_counter,
            replay_meta_by_event_id=historical_replay_meta_by_event_id,
            signal_accounts=len(samples),
        ),
        current_signal_group_breakdown=_build_current_signal_group_breakdown(
            observed_group_counter=observed_group_counter,
            signal_group_counter=signal_group_counter,
            multi_round_group_counter=multi_round_group_counter,
            historical_like_group_counter=historical_like_group_counter,
            group_historical_gap_counter=group_historical_gap_counter,
            group_pattern_counter=group_pattern_counter,
            group_historical_like_samples=group_historical_like_samples,
        ),
        top_status_messages=_build_top_status_messages(status_counter),
        recent_samples=samples[:10],
    )


def _load_success_snapshots_by_account_id(
    db: Session,
    *,
    account_ids: list[int],
) -> dict[int, list[AccountSnapshot]]:
    if not account_ids:
        return {}

    snapshots = list(
        db.scalars(
            select(AccountSnapshot)
            .where(
                AccountSnapshot.account_id.in_(account_ids),
                AccountSnapshot.snapshot_status == "success",
            )
            .order_by(
                AccountSnapshot.account_id.asc(),
                AccountSnapshot.checked_at.desc(),
                AccountSnapshot.id.desc(),
            )
        )
    )

    grouped: dict[int, list[AccountSnapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.account_id, []).append(snapshot)
    return grouped


def _build_current_signal_streak(
    *,
    account: Account,
    snapshots: list[AccountSnapshot],
) -> tuple[int, datetime | None]:
    if not snapshots:
        return 1, _ensure_utc(account.current_last_checked_at) if account.current_last_checked_at else None

    latest_checked_at = _ensure_utc(account.current_last_checked_at) if account.current_last_checked_at else None
    streak_count = 0
    signal_started_at: datetime | None = None

    for snapshot in snapshots:
        checked_at = _ensure_utc(snapshot.checked_at)
        if latest_checked_at is not None and checked_at > latest_checked_at:
            continue
        if not _extract_snapshot_signal_keys(snapshot):
            break
        streak_count += 1
        signal_started_at = checked_at

    if streak_count > 0:
        return streak_count, signal_started_at

    return 1, latest_checked_at


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


def _build_previous_gap_band_counts(counter: Counter[str]) -> list[ResearchBucketCount]:
    bands = [
        (key, label, counter.get(key, 0))
        for key, label in _PREVIOUS_GAP_BANDS
    ]
    return [ResearchBucketCount(key=key, label=label, count=count) for key, label, count in bands]


def _build_signal_breakdown(counter: Counter[str]) -> list[ResearchBucketCount]:
    items = [
        ResearchBucketCount(key=key, label=_SIGNAL_LABELS[key], count=count)
        for key, count in counter.items()
        if count > 0 and key in _SIGNAL_LABELS
    ]
    return sorted(items, key=lambda item: (-item.count, item.label))


def _build_signal_pattern_breakdown(counter: Counter[str]) -> list[ResearchBucketCount]:
    items = [
        ResearchBucketCount(
            key=pattern,
            label=_build_signal_pattern_label(pattern),
            count=count,
        )
        for pattern, count in counter.items()
        if count > 0 and pattern
    ]
    return sorted(items, key=lambda item: (-item.count, item.label))[:5]


def _build_signal_streak_breakdown(counter: Counter[str]) -> list[ResearchBucketCount]:
    buckets = [
        ("1", "仅最新 1 轮", counter.get("1", 0)),
        ("2_3", "连续 2-3 轮", counter.get("2_3", 0)),
        ("4_plus", "连续 4 轮以上", counter.get("4_plus", 0)),
    ]
    return [ResearchBucketCount(key=key, label=label, count=count) for key, label, count in buckets if count > 0]


def _build_historical_match_breakdown(counter: Counter[str]) -> list[ResearchBucketCount]:
    buckets = [
        ("exact_pattern", _HISTORICAL_MATCH_LABELS["exact_pattern"], counter.get("exact_pattern", 0)),
        ("covered_pattern", _HISTORICAL_MATCH_LABELS["covered_pattern"], counter.get("covered_pattern", 0)),
        ("partial_overlap", _HISTORICAL_MATCH_LABELS["partial_overlap"], counter.get("partial_overlap", 0)),
        ("no_overlap", _HISTORICAL_MATCH_LABELS["no_overlap"], counter.get("no_overlap", 0)),
        ("no_history", _HISTORICAL_MATCH_LABELS["no_history"], counter.get("no_history", 0)),
    ]
    return [ResearchBucketCount(key=key, label=label, count=count) for key, label, count in buckets if count > 0]


def _build_historical_like_event_count_breakdown(
    counter: Counter[str],
) -> list[ResearchBucketCount]:
    return [
        ResearchBucketCount(key=key, label=label, count=count)
        for key, label, count in (
            (key, label, counter.get(key, 0))
            for key, label in _HISTORICAL_LIKE_EVENT_COUNT_BUCKETS
        )
        if count > 0
    ]


def _build_historical_match_gap_breakdown(counter: Counter[str]) -> list[ResearchBucketCount]:
    if not any(counter.values()):
        return []
    return _build_previous_gap_band_counts(counter)


def _build_historical_replay_breakdown(
    *,
    replay_counter: Counter[int],
    exact_counter: Counter[int],
    covered_counter: Counter[int],
    partial_counter: Counter[int],
    replay_meta_by_event_id: dict[int, _HistoricalReplayBreakdownMeta],
    signal_accounts: int,
) -> list[ResearchHistoricalReplayBreakdownItem]:
    items: list[ResearchHistoricalReplayBreakdownItem] = []

    for event_id, matched_current_accounts in replay_counter.items():
        replay_meta = replay_meta_by_event_id.get(event_id)
        if replay_meta is None:
            continue

        items.append(
            ResearchHistoricalReplayBreakdownItem(
                event_id=event_id,
                event_account_id=replay_meta.event_account_id,
                event_account_name=replay_meta.event_account_name,
                event_time=replay_meta.event_time,
                historical_best_pattern=replay_meta.historical_best_pattern,
                historical_gap_bucket=replay_meta.historical_gap_bucket,
                historical_gap_label=replay_meta.historical_gap_label,
                historical_gap_minutes=replay_meta.historical_gap_minutes,
                matched_current_accounts=matched_current_accounts,
                matched_current_rate=_to_rate_percent(
                    numerator=matched_current_accounts,
                    denominator=signal_accounts,
                ),
                exact_match_accounts=exact_counter.get(event_id, 0),
                covered_match_accounts=covered_counter.get(event_id, 0),
                partial_overlap_accounts=partial_counter.get(event_id, 0),
            )
        )

    return sorted(
        items,
        key=lambda item: (
            -item.matched_current_accounts,
            -item.exact_match_accounts,
            -item.covered_match_accounts,
            -item.partial_overlap_accounts,
            _previous_gap_bucket_sort_key(item.historical_gap_bucket),
            item.historical_gap_minutes,
            item.event_account_name,
            -item.event_id,
        ),
    )[:5]


def _build_current_signal_group_breakdown(
    *,
    observed_group_counter: Counter[tuple[str | None, str | None]],
    signal_group_counter: Counter[tuple[str | None, str | None]],
    multi_round_group_counter: Counter[tuple[str | None, str | None]],
    historical_like_group_counter: Counter[tuple[str | None, str | None]],
    group_historical_gap_counter: dict[tuple[str | None, str | None], Counter[str]],
    group_pattern_counter: dict[tuple[str | None, str | None], Counter[str]],
    group_historical_like_samples: dict[
        tuple[str | None, str | None],
        list[ResearchCurrentSignalGroupSample],
    ],
) -> list[ResearchCurrentSignalGroupBreakdownItem]:
    items: list[ResearchCurrentSignalGroupBreakdownItem] = []

    for group_key, signal_accounts in signal_group_counter.items():
        provider, account_type = group_key
        observed_accounts = observed_group_counter.get(group_key, 0)
        top_historical_gap_bucket = _pick_top_historical_gap_bucket(
            group_historical_gap_counter.get(group_key, Counter())
        )
        top_historical_gap_label = (
            _PREVIOUS_GAP_BAND_LABELS[top_historical_gap_bucket]
            if top_historical_gap_bucket is not None
            else None
        )
        top_historical_gap_count = (
            group_historical_gap_counter.get(group_key, Counter()).get(top_historical_gap_bucket, 0)
            if top_historical_gap_bucket is not None
            else 0
        )
        top_pattern_key = _pick_top_signal_pattern_key(group_pattern_counter.get(group_key, Counter()))
        top_pattern = None if top_pattern_key is None else _build_signal_pattern_label(top_pattern_key)
        top_historical_like_samples = sorted(
            group_historical_like_samples.get(group_key, []),
            key=lambda item: _build_current_signal_sort_key(
                historical_match_level=item.historical_match_level,
                historical_match_rate=item.historical_match_rate,
                consecutive_signal_snapshots=item.consecutive_signal_snapshots,
                signal_label_count=len(item.signal_labels),
                current_weekly_used_percent=None,
                current_short_used_percent=None,
                current_last_checked_at=item.current_last_checked_at,
                account_name=item.account_name,
            ),
        )[:3]
        items.append(
            ResearchCurrentSignalGroupBreakdownItem(
                label=_build_combo_label(provider=provider, account_type=account_type),
                provider=provider,
                account_type=account_type,
                observed_accounts=observed_accounts,
                signal_accounts=signal_accounts,
                signal_rate=_to_rate_percent(
                    numerator=signal_accounts,
                    denominator=observed_accounts,
                ),
                multi_round_signal_accounts=multi_round_group_counter.get(group_key, 0),
                historical_like_accounts=historical_like_group_counter.get(group_key, 0),
                historical_like_rate=_to_rate_percent(
                    numerator=historical_like_group_counter.get(group_key, 0),
                    denominator=signal_accounts,
                ),
                top_historical_gap_bucket=top_historical_gap_bucket,
                top_historical_gap_label=top_historical_gap_label,
                top_historical_gap_count=top_historical_gap_count,
                top_signal_pattern_key=top_pattern_key,
                top_signal_pattern=top_pattern,
                top_historical_like_samples=top_historical_like_samples,
            )
        )

    return sorted(
        items,
        key=lambda item: (
            -item.historical_like_accounts,
            -item.historical_like_rate,
            _previous_gap_bucket_sort_key(item.top_historical_gap_bucket),
            -item.top_historical_gap_count,
            -item.signal_accounts,
            -item.multi_round_signal_accounts,
            -item.signal_rate,
            -item.observed_accounts,
            item.label,
        ),
    )


def _build_top_status_messages(counter: Counter[str]) -> list[ResearchBucketCount]:
    items = [
        ResearchBucketCount(key=message, label=message, count=count)
        for message, count in counter.items()
    ]
    return sorted(items, key=lambda item: (-item.count, item.label))[:5]


def _build_signal_pattern_label(pattern: str) -> str:
    return " / ".join(_SIGNAL_LABELS[key] for key in pattern.split("|") if key in _SIGNAL_LABELS)


def normalize_research_signal_pattern_key(pattern: str) -> str:
    parts = [part.strip() for part in pattern.split("|") if part.strip()]
    if not parts or len(parts) != len(set(parts)):
        raise ValueError(pattern)

    if any(part not in _SIGNAL_LABELS for part in parts):
        raise ValueError(pattern)

    normalized_parts = [key for key in RESEARCH_SIGNAL_KEYS if key in parts]
    if not normalized_parts:
        raise ValueError(pattern)

    return "|".join(normalized_parts)


def _pick_top_signal_pattern_key(counter: Counter[str]) -> str | None:
    if not counter:
        return None

    pattern, _ = min(
        counter.items(),
        key=lambda item: (-item[1], _build_signal_pattern_label(item[0]), item[0]),
    )
    return pattern


def _pick_top_historical_gap_bucket(counter: Counter[str]) -> str | None:
    if not counter:
        return None

    gap_bucket, _ = min(
        counter.items(),
        key=lambda item: (-item[1], _previous_gap_bucket_sort_key(item[0]), item[0]),
    )
    return gap_bucket


_SIGNAL_LABELS = {
    "weekly_ge_90": "周额度 >= 90%",
    "short_ge_90": "短周期 >= 90%",
    "limit_reached": "limit_reached=true",
    "allowed_false": "allowed=false",
    "remaining_empty": "remaining <= 0",
    "status_message_present": "存在 status_message",
}
RESEARCH_SIGNAL_KEYS = tuple(_SIGNAL_LABELS)
_PREVIOUS_GAP_BANDS = (
    ("lt_15m", "15 分钟内"),
    ("15m_1h", "15-60 分钟"),
    ("1h_6h", "1-6 小时"),
    ("6h_24h", "6-24 小时"),
    ("24h_plus", "24 小时以上"),
)
RESEARCH_PRE_401_GAP_BUCKET_KEYS = tuple(key for key, _ in _PREVIOUS_GAP_BANDS)
_PREVIOUS_GAP_BAND_LABELS = dict(_PREVIOUS_GAP_BANDS)
_PREVIOUS_GAP_BAND_ORDER = {
    key: index for index, (key, _) in enumerate(_PREVIOUS_GAP_BANDS)
}
_HISTORICAL_MATCH_LABELS = {
    "exact_pattern": "与历史前序完全同模式",
    "covered_pattern": "被历史前序模式覆盖",
    "partial_overlap": "仅部分信号重合",
    "no_overlap": "与历史前序未重合",
    "no_history": "暂无历史 401 样本",
}
RESEARCH_HISTORICAL_MATCH_LEVELS = tuple(_HISTORICAL_MATCH_LABELS)
_HISTORICAL_MATCH_PRIORITY = {
    "exact_pattern": 0,
    "covered_pattern": 1,
    "partial_overlap": 2,
    "no_overlap": 3,
    "no_history": 4,
}
_HISTORICAL_LIKE_LEVELS = frozenset({"exact_pattern", "covered_pattern"})
_HISTORICAL_LIKE_EVENT_COUNT_BUCKETS = (
    ("1", "1 条历史高贴近事件"),
    ("2_3", "2-3 条历史高贴近事件"),
    ("4_plus", "4 条及以上历史高贴近事件"),
)
RESEARCH_HISTORICAL_LIKE_EVENT_COUNT_BUCKET_KEYS = tuple(
    key for key, _ in _HISTORICAL_LIKE_EVENT_COUNT_BUCKETS
)


@dataclass(slots=True)
class _HistoricalSignalMatchResult:
    level: str
    rate: float
    like_event_count: int
    best_pattern_label: str | None
    overlap_signal_labels: list[str]
    current_only_signal_labels: list[str]
    historical_only_signal_labels: list[str]
    best_event_id: int | None
    best_event_account_id: int | None
    best_event_account_name: str | None
    best_event_time: datetime | None
    best_gap_bucket: str | None
    best_gap_label: str | None
    best_gap_minutes: int | None


@dataclass(slots=True)
class _HistoricalReplayBreakdownMeta:
    event_id: int
    event_account_id: int
    event_account_name: str
    event_time: datetime
    historical_best_pattern: str
    historical_gap_bucket: str
    historical_gap_label: str
    historical_gap_minutes: int


@dataclass(slots=True)
class _HistoricalSignalCandidate:
    event_id: int
    event_account_id: int
    event_account_name: str
    event_time: datetime
    signal_keys: list[str]
    pattern_key: str
    pattern_label: str
    previous_gap_bucket: str
    previous_gap_label: str
    previous_gap_minutes: int


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


def _extract_snapshot_signal_keys(snapshot: AccountSnapshot) -> list[str]:
    signal_keys: list[str] = []

    if _decimal_gte(snapshot.weekly_used_percent, Decimal("90")):
        signal_keys.append("weekly_ge_90")
    if _decimal_gte(snapshot.short_used_percent, Decimal("90")):
        signal_keys.append("short_ge_90")
    if snapshot.limit_reached is True:
        signal_keys.append("limit_reached")
    if snapshot.allowed is False:
        signal_keys.append("allowed_false")
    if snapshot.remaining is not None and snapshot.remaining <= 0:
        signal_keys.append("remaining_empty")
    if (snapshot.status_message or "").strip():
        signal_keys.append("status_message_present")

    return signal_keys


def _evaluate_historical_signal_match(
    *,
    signal_keys: list[str],
    historical_candidates: list[_HistoricalSignalCandidate],
) -> _HistoricalSignalMatchResult:
    if not historical_candidates:
        return _HistoricalSignalMatchResult(
            level="no_history",
            rate=0.0,
            like_event_count=0,
            best_pattern_label=None,
            overlap_signal_labels=[],
            current_only_signal_labels=[],
            historical_only_signal_labels=[],
            best_event_id=None,
            best_event_account_id=None,
            best_event_account_name=None,
            best_event_time=None,
            best_gap_bucket=None,
            best_gap_label=None,
            best_gap_minutes=None,
        )

    current_signal_set = frozenset(signal_keys)
    if not current_signal_set:
        return _HistoricalSignalMatchResult(
            level="no_overlap",
            rate=0.0,
            like_event_count=0,
            best_pattern_label=None,
            overlap_signal_labels=[],
            current_only_signal_labels=[],
            historical_only_signal_labels=[],
            best_event_id=None,
            best_event_account_id=None,
            best_event_account_name=None,
            best_event_time=None,
            best_gap_bucket=None,
            best_gap_label=None,
            best_gap_minutes=None,
        )

    best_candidate: tuple[int, int, int, int, str, str] | None = None
    best_signal_candidate: _HistoricalSignalCandidate | None = None
    best_matched_count = 0
    best_is_exact = False
    best_is_covered = False
    like_event_count = 0

    for historical_candidate in historical_candidates:
        historical_signal_set = frozenset(historical_candidate.signal_keys)
        matched_count = len(current_signal_set & historical_signal_set)
        if matched_count <= 0:
            continue

        is_exact = historical_signal_set == current_signal_set
        is_covered = current_signal_set.issubset(historical_signal_set)
        if is_exact or is_covered:
            like_event_count += 1
        candidate = (
            -matched_count,
            -int(is_exact),
            -int(is_covered),
            len(historical_signal_set),
            historical_candidate.pattern_label,
            historical_candidate.pattern_key,
        )
        candidate_is_better = best_candidate is None or candidate < best_candidate
        candidate_has_newer_event = (
            best_signal_candidate is not None
            and candidate == best_candidate
            and (
                historical_candidate.event_time,
                historical_candidate.event_id,
            )
            > (
                best_signal_candidate.event_time,
                best_signal_candidate.event_id,
            )
        )
        if candidate_is_better or candidate_has_newer_event:
            best_candidate = candidate
            best_signal_candidate = historical_candidate
            best_matched_count = matched_count
            best_is_exact = is_exact
            best_is_covered = is_covered

    if best_candidate is None or best_signal_candidate is None:
        return _HistoricalSignalMatchResult(
            level="no_overlap",
            rate=0.0,
            like_event_count=like_event_count,
            best_pattern_label=None,
            overlap_signal_labels=[],
            current_only_signal_labels=[],
            historical_only_signal_labels=[],
            best_event_id=None,
            best_event_account_id=None,
            best_event_account_name=None,
            best_event_time=None,
            best_gap_bucket=None,
            best_gap_label=None,
            best_gap_minutes=None,
        )

    best_historical_signal_set = frozenset(best_signal_candidate.signal_keys)
    overlap_signal_keys = [
        key for key in RESEARCH_SIGNAL_KEYS if key in current_signal_set and key in best_historical_signal_set
    ]
    current_only_signal_keys = [
        key for key in RESEARCH_SIGNAL_KEYS if key in current_signal_set and key not in best_historical_signal_set
    ]
    historical_only_signal_keys = [
        key for key in RESEARCH_SIGNAL_KEYS if key in best_historical_signal_set and key not in current_signal_set
    ]

    if best_is_exact:
        level = "exact_pattern"
    elif best_is_covered and best_matched_count == len(current_signal_set):
        level = "covered_pattern"
    else:
        level = "partial_overlap"

    return _HistoricalSignalMatchResult(
        level=level,
        rate=_to_rate_percent(
            numerator=best_matched_count,
            denominator=len(current_signal_set),
        ),
        like_event_count=like_event_count,
        best_pattern_label=best_signal_candidate.pattern_label,
        overlap_signal_labels=_signal_labels_from_keys(overlap_signal_keys),
        current_only_signal_labels=_signal_labels_from_keys(current_only_signal_keys),
        historical_only_signal_labels=_signal_labels_from_keys(historical_only_signal_keys),
        best_event_id=best_signal_candidate.event_id,
        best_event_account_id=best_signal_candidate.event_account_id,
        best_event_account_name=best_signal_candidate.event_account_name,
        best_event_time=best_signal_candidate.event_time,
        best_gap_bucket=best_signal_candidate.previous_gap_bucket,
        best_gap_label=best_signal_candidate.previous_gap_label,
        best_gap_minutes=best_signal_candidate.previous_gap_minutes,
    )


def _build_historical_signal_candidates(
    event_rows: list[tuple[AccountEvent, Account, AccountSnapshot | None]],
) -> list[_HistoricalSignalCandidate]:
    candidates: list[_HistoricalSignalCandidate] = []

    for event, account, previous_snapshot in event_rows:
        if previous_snapshot is None:
            continue

        signal_keys = _extract_snapshot_signal_keys(previous_snapshot)
        if not signal_keys:
            continue

        pattern_key = "|".join(signal_keys)
        previous_gap_bucket = _bucket_previous_gap(
            event_time=event.event_time,
            previous_checked_at=previous_snapshot.checked_at,
        )
        candidates.append(
            _HistoricalSignalCandidate(
                event_id=event.id,
                event_account_id=account.id,
                event_account_name=account.name,
                event_time=_ensure_utc(event.event_time),
                signal_keys=signal_keys,
                pattern_key=pattern_key,
                pattern_label=_build_signal_pattern_label(pattern_key),
                previous_gap_bucket=previous_gap_bucket,
                previous_gap_label=_PREVIOUS_GAP_BAND_LABELS[previous_gap_bucket],
                previous_gap_minutes=_build_gap_minutes(
                    event_time=event.event_time,
                    previous_checked_at=previous_snapshot.checked_at,
                ),
            )
        )

    return candidates


def _build_status_message_excerpt(value: str | None, *, limit: int = 120) -> str | None:
    if value is None:
        return None

    normalized = _normalize_status_message_text(value)
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _normalize_status_message_filter(value: str | None) -> str | None:
    if value is None:
        return None
    return _build_status_message_excerpt(value)


def _normalize_status_message_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        return ""

    parsed = _extract_status_message_payload(normalized)
    if parsed:
        normalized = parsed

    return " ".join(normalized.split())


def _extract_status_message_payload(value: str) -> str | None:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        message = _first_non_empty_text(
            error_payload.get("message"),
            error_payload.get("detail"),
        )
        error_type = _first_non_empty_text(
            error_payload.get("type"),
            error_payload.get("code"),
        )
        if message and error_type:
            return f"{error_type}: {message}"
        if message:
            return message
        if error_type:
            return error_type

    message = _first_non_empty_text(payload.get("message"), payload.get("detail"))
    if message:
        return message

    return _first_non_empty_text(payload.get("error"))


def _first_non_empty_text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str):
            normalized = " ".join(value.split())
            if normalized:
                return normalized
    return None


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


def _bucket_signal_streak(value: int) -> str:
    if value <= 1:
        return "1"
    if value <= 3:
        return "2_3"
    return "4_plus"


def _bucket_historical_like_event_count(value: int) -> str | None:
    if value <= 0:
        return None
    if value == 1:
        return "1"
    if value <= 3:
        return "2_3"
    return "4_plus"


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


def _signal_labels_from_keys(keys: list[str]) -> list[str]:
    return [_SIGNAL_LABELS[key] for key in keys if key in _SIGNAL_LABELS]


def _historical_match_sort_key(level: str) -> int:
    return _HISTORICAL_MATCH_PRIORITY.get(level, len(_HISTORICAL_MATCH_PRIORITY))


def _build_current_signal_sort_key(
    *,
    historical_match_level: str,
    historical_match_rate: float,
    consecutive_signal_snapshots: int,
    signal_label_count: int,
    current_weekly_used_percent: Decimal | None,
    current_short_used_percent: Decimal | None,
    current_last_checked_at: datetime | None,
    account_name: str,
) -> tuple[int, float, int, int, Decimal, Decimal, float, str]:
    return (
        _historical_match_sort_key(historical_match_level),
        -historical_match_rate,
        -consecutive_signal_snapshots,
        -signal_label_count,
        -(current_weekly_used_percent or Decimal("-1")),
        -(current_short_used_percent or Decimal("-1")),
        -_datetime_to_timestamp(current_last_checked_at),
        account_name,
    )


def _build_gap_minutes(*, event_time: datetime, previous_checked_at: datetime) -> int:
    gap_seconds = (_ensure_utc(event_time) - _ensure_utc(previous_checked_at)).total_seconds()
    if gap_seconds <= 0:
        return 0
    return int(gap_seconds // 60)


def _bucket_previous_gap(*, event_time: datetime, previous_checked_at: datetime) -> str:
    gap = _ensure_utc(event_time) - _ensure_utc(previous_checked_at)

    if gap < timedelta(minutes=15):
        return "lt_15m"
    if gap < timedelta(hours=1):
        return "15m_1h"
    if gap < timedelta(hours=6):
        return "1h_6h"
    if gap < timedelta(hours=24):
        return "6h_24h"
    return "24h_plus"


def _previous_gap_bucket_sort_key(bucket: str | None) -> int:
    if bucket is None:
        return len(_PREVIOUS_GAP_BAND_ORDER)
    return _PREVIOUS_GAP_BAND_ORDER.get(bucket, len(_PREVIOUS_GAP_BAND_ORDER))
