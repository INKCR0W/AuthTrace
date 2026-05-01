from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.account import Account
from app.models.account_event import AccountEvent


@dataclass(slots=True)
class SyncedAuthFile:
    account: Account
    auth_file: dict[str, Any]
    eligible: bool


@dataclass(slots=True)
class AuthFileSyncResult:
    total_accounts: int
    synced_accounts: int
    eligible_accounts: int
    missing_auth_index_accounts: int
    synced_auth_files: list[SyncedAuthFile]

    @property
    def skipped_accounts(self) -> int:
        return self.total_accounts - self.synced_accounts

    @property
    def eligible_auth_files(self) -> list[SyncedAuthFile]:
        return [item for item in self.synced_auth_files if item.eligible]


@dataclass(slots=True)
class AccountListFilters:
    provider: str | None = None
    account_type: str | None = None
    current_is_401: bool | None = None
    current_invalid_quota: bool | None = None
    disabled: bool | None = None
    include_deleted: bool = False
    last_checked_from: datetime | None = None
    last_checked_to: datetime | None = None
    limit: int = 50
    offset: int = 0


@dataclass(slots=True)
class AccountCohortBreakdown:
    label: str
    provider: str | None
    account_type: str | None
    total_accounts: int
    active_accounts: int
    disabled_accounts: int
    current_401_accounts: int
    current_invalid_quota_accounts: int
    became_401_events_last_24h: int
    quota_exhausted_events_last_24h: int
    checked_accounts_last_24h: int
    high_weekly_accounts: int
    high_short_accounts: int
    current_limit_reached_accounts: int
    current_blocked_accounts: int
    current_401_rate: float
    current_invalid_quota_rate: float


@dataclass(slots=True)
class AccountCohortUsagePosition:
    weekly_compared_accounts: int
    weekly_used_percent: Decimal | None
    weekly_rank_desc: int | None
    short_compared_accounts: int
    short_used_percent: Decimal | None
    short_rank_desc: int | None


@dataclass(slots=True)
class AccountResearchSummary:
    provider_cohort: AccountCohortBreakdown
    account_type_cohort: AccountCohortBreakdown
    provider_account_type_cohort: AccountCohortBreakdown
    usage_position: AccountCohortUsagePosition


def list_accounts(
    db: Session,
    *,
    filters: AccountListFilters,
) -> tuple[list[Account], int]:
    filtered_statement = _apply_account_filters(select(Account), filters=filters)
    filtered_count_statement = _apply_account_filters(select(func.count(Account.id)), filters=filters)

    items = list(
        db.scalars(
            filtered_statement.order_by(Account.current_last_checked_at.desc(), Account.id.desc())
            .offset(filters.offset)
            .limit(filters.limit)
        ).all()
    )
    total = int(db.scalar(filtered_count_statement) or 0)
    return items, total


def get_account_research_summary(
    db: Session,
    *,
    account: Account,
) -> AccountResearchSummary:
    last_24h_start = datetime.now(timezone.utc) - timedelta(hours=24)
    provider_label = account.provider or "未标记 provider"
    account_type_label = account.account_type or "未标记类型"

    return AccountResearchSummary(
        provider_cohort=_build_account_cohort_breakdown(
            db,
            label=provider_label,
            provider=account.provider,
            account_type=None,
            last_24h_start=last_24h_start,
            match_provider=True,
            match_account_type=False,
        ),
        account_type_cohort=_build_account_cohort_breakdown(
            db,
            label=account_type_label,
            provider=None,
            account_type=account.account_type,
            last_24h_start=last_24h_start,
            match_provider=False,
            match_account_type=True,
        ),
        provider_account_type_cohort=_build_account_cohort_breakdown(
            db,
            label=f"{provider_label} / {account_type_label}",
            provider=account.provider,
            account_type=account.account_type,
            last_24h_start=last_24h_start,
            match_provider=True,
            match_account_type=True,
        ),
        usage_position=_build_usage_position(
            db,
            provider=account.provider,
            account_type=account.account_type,
            weekly_used_percent=account.current_weekly_used_percent,
            short_used_percent=account.current_short_used_percent,
        ),
    )


def sync_accounts_from_auth_files(
    db: Session,
    *,
    source_id: int,
    auth_files: list[dict[str, Any]],
    seen_at: datetime,
    settings: Settings,
) -> AuthFileSyncResult:
    existing_accounts = db.scalars(select(Account).where(Account.source_id == source_id)).all()
    existing_by_auth_index = {account.auth_index: account for account in existing_accounts}

    incoming_auth_indices: set[str] = set()
    synced_accounts = 0
    eligible_accounts = 0
    missing_auth_index_accounts = 0
    synced_auth_files: list[SyncedAuthFile] = []

    for item in auth_files:
        auth_index = _normalize_optional_text(item.get("auth_index"))
        if auth_index is None:
            missing_auth_index_accounts += 1
            continue

        is_eligible = _is_eligible_auth_file(item, settings)
        if is_eligible:
            eligible_accounts += 1

        incoming_auth_indices.add(auth_index)
        account = existing_by_auth_index.get(auth_index)
        if account is None:
            account = Account(
                source_id=source_id,
                auth_index=auth_index,
                name=_normalize_optional_text(item.get("name")) or auth_index,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
            db.add(account)
            existing_by_auth_index[auth_index] = account

        account.name = _normalize_optional_text(item.get("name")) or auth_index
        account.account = _normalize_optional_text(item.get("account"))
        account.email = _normalize_optional_text(item.get("email"))
        account.account_type = _extract_item_type(item)
        account.provider = _normalize_optional_text(item.get("provider"))
        account.chatgpt_account_id = _extract_chatgpt_account_id(item)
        account.disabled = bool(item.get("disabled"))
        account.upstream_status = _normalize_optional_text(item.get("status"))
        account.status_message = _stringify_text_value(item.get("status_message"))
        account.last_seen_at = seen_at
        account.source_deleted_at = None
        synced_auth_files.append(SyncedAuthFile(account=account, auth_file=item, eligible=is_eligible))
        synced_accounts += 1

    for account in existing_accounts:
        if account.auth_index not in incoming_auth_indices:
            account.source_deleted_at = seen_at

    db.flush()
    return AuthFileSyncResult(
        total_accounts=len(auth_files),
        synced_accounts=synced_accounts,
        eligible_accounts=eligible_accounts,
        missing_auth_index_accounts=missing_auth_index_accounts,
        synced_auth_files=synced_auth_files,
    )


def _apply_account_filters(statement: Select, *, filters: AccountListFilters) -> Select:
    if filters.provider:
        statement = statement.where(Account.provider == filters.provider)
    if filters.account_type:
        statement = statement.where(Account.account_type == filters.account_type)
    if filters.current_is_401 is not None:
        statement = statement.where(Account.current_is_401 == filters.current_is_401)
    if filters.current_invalid_quota is not None:
        statement = statement.where(Account.current_invalid_quota == filters.current_invalid_quota)
    if filters.disabled is not None:
        statement = statement.where(Account.disabled == filters.disabled)
    if not filters.include_deleted:
        statement = statement.where(Account.source_deleted_at.is_(None))
    if filters.last_checked_from is not None:
        statement = statement.where(Account.current_last_checked_at >= filters.last_checked_from)
    if filters.last_checked_to is not None:
        statement = statement.where(Account.current_last_checked_at <= filters.last_checked_to)
    return statement


def _build_account_cohort_breakdown(
    db: Session,
    *,
    label: str,
    provider: str | None,
    account_type: str | None,
    last_24h_start: datetime,
    match_provider: bool,
    match_account_type: bool,
) -> AccountCohortBreakdown:
    account_conditions = [Account.source_deleted_at.is_(None)]
    if match_provider:
        account_conditions.append(_match_optional_text(Account.provider, provider))
    if match_account_type:
        account_conditions.append(_match_optional_text(Account.account_type, account_type))

    account_row = db.execute(
        select(
            func.count(Account.id).label("total_accounts"),
            func.sum(case((Account.disabled.is_(False), 1), else_=0)).label("active_accounts"),
            func.sum(case((Account.disabled.is_(True), 1), else_=0)).label("disabled_accounts"),
            func.sum(case((Account.current_is_401.is_(True), 1), else_=0)).label("current_401_accounts"),
            func.sum(
                case((Account.current_invalid_quota.is_(True), 1), else_=0)
            ).label("current_invalid_quota_accounts"),
            func.sum(
                case((Account.current_last_checked_at >= last_24h_start, 1), else_=0)
            ).label("checked_accounts_last_24h"),
            func.sum(
                case((Account.current_weekly_used_percent >= 80, 1), else_=0)
            ).label("high_weekly_accounts"),
            func.sum(
                case((Account.current_short_used_percent >= 80, 1), else_=0)
            ).label("high_short_accounts"),
            func.sum(
                case((Account.current_limit_reached.is_(True), 1), else_=0)
            ).label("current_limit_reached_accounts"),
            func.sum(
                case((Account.current_allowed.is_(False), 1), else_=0)
            ).label("current_blocked_accounts"),
        ).where(*account_conditions)
    ).one()

    event_rows = db.execute(
        select(
            AccountEvent.event_type,
            func.count(AccountEvent.id).label("event_count"),
        )
        .select_from(AccountEvent)
        .join(Account, Account.id == AccountEvent.account_id)
        .where(
            *account_conditions,
            AccountEvent.event_time >= last_24h_start,
            AccountEvent.event_type.in_(("became_401", "quota_exhausted")),
        )
        .group_by(AccountEvent.event_type)
    ).all()
    event_counts = {str(row.event_type): int(row.event_count or 0) for row in event_rows}

    total_accounts = int(account_row.total_accounts or 0)
    current_401_accounts = int(account_row.current_401_accounts or 0)
    current_invalid_quota_accounts = int(account_row.current_invalid_quota_accounts or 0)

    return AccountCohortBreakdown(
        label=label,
        provider=provider,
        account_type=account_type,
        total_accounts=total_accounts,
        active_accounts=int(account_row.active_accounts or 0),
        disabled_accounts=int(account_row.disabled_accounts or 0),
        current_401_accounts=current_401_accounts,
        current_invalid_quota_accounts=current_invalid_quota_accounts,
        became_401_events_last_24h=event_counts.get("became_401", 0),
        quota_exhausted_events_last_24h=event_counts.get("quota_exhausted", 0),
        checked_accounts_last_24h=int(account_row.checked_accounts_last_24h or 0),
        high_weekly_accounts=int(account_row.high_weekly_accounts or 0),
        high_short_accounts=int(account_row.high_short_accounts or 0),
        current_limit_reached_accounts=int(account_row.current_limit_reached_accounts or 0),
        current_blocked_accounts=int(account_row.current_blocked_accounts or 0),
        current_401_rate=_to_rate_percent(
            numerator=current_401_accounts,
            denominator=total_accounts,
        ),
        current_invalid_quota_rate=_to_rate_percent(
            numerator=current_invalid_quota_accounts,
            denominator=total_accounts,
        ),
    )


def _build_usage_position(
    db: Session,
    *,
    provider: str | None,
    account_type: str | None,
    weekly_used_percent: Decimal | None,
    short_used_percent: Decimal | None,
) -> AccountCohortUsagePosition:
    statement = select(Account.current_weekly_used_percent, Account.current_short_used_percent).where(
        Account.source_deleted_at.is_(None),
        Account.disabled.is_(False),
        _match_optional_text(Account.provider, provider),
        _match_optional_text(Account.account_type, account_type),
    )
    peer_rows = db.execute(statement).all()
    weekly_values = [row.current_weekly_used_percent for row in peer_rows if row.current_weekly_used_percent is not None]
    short_values = [row.current_short_used_percent for row in peer_rows if row.current_short_used_percent is not None]

    return AccountCohortUsagePosition(
        weekly_compared_accounts=len(weekly_values),
        weekly_used_percent=weekly_used_percent,
        weekly_rank_desc=_rank_desc(values=weekly_values, current_value=weekly_used_percent),
        short_compared_accounts=len(short_values),
        short_used_percent=short_used_percent,
        short_rank_desc=_rank_desc(values=short_values, current_value=short_used_percent),
    )


def _extract_item_type(item: dict[str, Any]) -> str | None:
    return _normalize_optional_text(item.get("type")) or _normalize_optional_text(item.get("typo"))


def _extract_chatgpt_account_id(item: dict[str, Any]) -> str | None:
    for key in ("chatgpt_account_id", "chatgptAccountId", "account_id", "accountId"):
        value = _normalize_optional_text(item.get(key))
        if value is not None:
            return value
    return None


def _is_eligible_auth_file(item: dict[str, Any], settings: Settings) -> bool:
    if bool(item.get("disabled")):
        return False
    if bool(item.get("standby")):
        return False
    if _normalize_optional_text(item.get("auth_index")) is None:
        return False

    status = (_normalize_optional_text(item.get("status")) or "unknown").lower()
    if status not in {"active", "unknown", "error"}:
        return False

    item_type = (_extract_item_type(item) or "").lower()
    provider = (_normalize_optional_text(item.get("provider")) or "").lower()
    target_type = (settings.management_target_type or "").lower()
    target_provider = (settings.management_provider or "").lower()

    if target_type and item_type != target_type:
        return False
    if target_provider and provider != target_provider:
        return False

    return True


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _stringify_text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return json.dumps(value, ensure_ascii=False)


def _match_optional_text(column: Any, value: str | None) -> Any:
    if value is None:
        return column.is_(None)
    return column == value


def _to_rate_percent(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _rank_desc(
    *,
    values: list[Decimal],
    current_value: Decimal | None,
) -> int | None:
    if current_value is None or not values:
        return None
    higher_count = sum(1 for value in values if value > current_value)
    return higher_count + 1
