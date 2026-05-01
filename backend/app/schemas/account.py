from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AccountSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    auth_index: str
    name: str
    account: str | None = None
    email: str | None = None
    account_type: str | None = None
    provider: str | None = None
    chatgpt_account_id: str | None = None
    disabled: bool
    upstream_status: str | None = None
    status_message: str | None = None
    current_status_code: int | None = None
    current_is_401: bool
    current_invalid_quota: bool
    current_weekly_used_percent: Decimal | None = None
    current_weekly_reset_at: datetime | None = None
    current_short_used_percent: Decimal | None = None
    current_short_reset_at: datetime | None = None
    current_remaining: Decimal | None = None
    current_limit_reached: bool | None = None
    current_allowed: bool | None = None
    current_last_checked_at: datetime | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    source_deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AccountSnapshotSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    checked_at: datetime
    snapshot_status: str
    probe_status_code: int | None = None
    is_401: bool
    invalid_quota: bool
    quota_source: str | None = None
    weekly_used_percent: Decimal | None = None
    weekly_reset_at: datetime | None = None
    short_used_percent: Decimal | None = None
    short_reset_at: datetime | None = None
    remaining: Decimal | None = None
    limit_reached: bool | None = None
    allowed: bool | None = None
    status_message: str | None = None
    error_message: str | None = None


class AccountEventSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    event_time: datetime
    related_snapshot_id: int
    previous_snapshot_id: int | None = None
    from_status_code: int | None = None
    to_status_code: int | None = None
    from_is_401: bool | None = None
    to_is_401: bool | None = None
    from_invalid_quota: bool | None = None
    to_invalid_quota: bool | None = None
    from_disabled: bool | None = None
    to_disabled: bool | None = None
    note: str | None = None
    created_at: datetime


class AccountCohortBreakdown(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    provider: str | None = None
    account_type: str | None = None
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


class AccountCohortUsagePosition(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weekly_compared_accounts: int
    weekly_used_percent: Decimal | None = None
    weekly_rank_desc: int | None = None
    short_compared_accounts: int
    short_used_percent: Decimal | None = None
    short_rank_desc: int | None = None


class AccountRiskSignal(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    tone: str
    detail: str


class AccountRiskOverview(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: str
    headline: str
    summary: str
    signal_count: int
    signals: list[AccountRiskSignal] = Field(default_factory=list)


class AccountCohortTrendPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bucket_start: datetime
    snapshot_count: int
    is_401_count: int
    invalid_quota_count: int
    failed_count: int
    high_weekly_count: int
    high_short_count: int


class AccountListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AccountSummary]


class AccountDetailResponse(BaseModel):
    account: AccountSummary
    recent_snapshots: list[AccountSnapshotSummary] = Field(default_factory=list)
    recent_events: list[AccountEventSummary] = Field(default_factory=list)
    provider_cohort: AccountCohortBreakdown
    account_type_cohort: AccountCohortBreakdown
    provider_account_type_cohort: AccountCohortBreakdown
    cohort_usage_position: AccountCohortUsagePosition
    risk_overview: AccountRiskOverview
    provider_account_type_trend: list[AccountCohortTrendPoint] = Field(default_factory=list)
