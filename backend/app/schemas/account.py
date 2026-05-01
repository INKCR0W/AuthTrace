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


class AccountListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AccountSummary]


class AccountDetailResponse(BaseModel):
    account: AccountSummary
    recent_snapshots: list[AccountSnapshotSummary] = Field(default_factory=list)
    recent_events: list[AccountEventSummary] = Field(default_factory=list)
