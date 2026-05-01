from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OverviewTrendPoint(BaseModel):
    bucket_start: datetime
    became_401_count: int


class DimensionBreakdownItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    value: str | None = None
    label: str
    total_accounts: int
    active_accounts: int
    disabled_accounts: int
    current_401_accounts: int
    current_invalid_quota_accounts: int
    became_401_events_last_24h: int
    current_401_rate: float
    current_invalid_quota_rate: float


class LatestScanJobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    status: str
    trigger_mode: str
    scan_started_at: datetime
    scan_finished_at: datetime | None = None
    total_accounts: int
    eligible_accounts: int
    scanned_accounts: int
    success_accounts: int
    failed_accounts: int
    new_401_events: int
    new_quota_events: int
    duration_ms: int | None = None
    error_message: str | None = None


class DashboardOverviewResponse(BaseModel):
    total_accounts: int
    active_accounts: int
    disabled_accounts: int
    deleted_accounts: int
    current_401_accounts: int
    current_invalid_quota_accounts: int
    new_401_events_last_24h: int
    new_quota_events_last_24h: int
    recent_401_trend: list[OverviewTrendPoint] = Field(default_factory=list)
    provider_breakdown: list[DimensionBreakdownItem] = Field(default_factory=list)
    account_type_breakdown: list[DimensionBreakdownItem] = Field(default_factory=list)
    latest_scan_job: LatestScanJobSummary | None = None
