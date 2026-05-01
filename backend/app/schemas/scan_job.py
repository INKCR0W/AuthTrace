from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScanJobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    trigger_mode: str
    status: str
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


class ScanJobListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ScanJobSummary] = Field(default_factory=list)


class ScanJobSnapshotStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_snapshots: int
    success_snapshots: int
    partial_failed_snapshots: int
    failed_snapshots: int
    is_401_snapshots: int
    invalid_quota_snapshots: int


class ScanJobDiagnosticBucket(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    count: int


class ScanJobDiagnosticSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    abnormal_probe_status_samples: int
    abnormal_probe_status_breakdown: list[ScanJobDiagnosticBucket] = Field(default_factory=list)
    top_failure_reasons: list[ScanJobDiagnosticBucket] = Field(default_factory=list)


class ScanJobAccountRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    auth_index: str
    provider: str | None = None
    account_type: str | None = None
    disabled: bool


class ScanJobSnapshotSample(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    scan_job_id: int
    checked_at: datetime
    snapshot_status: str
    probe_status_code: int | None = None
    is_401: bool
    quota_status_code: int | None = None
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
    raw_auth_file_json: dict[str, Any] | None = None
    raw_usage_json: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    account: ScanJobAccountRef


class ScanJobDetailResponse(BaseModel):
    item: ScanJobSummary
    snapshot_stats: ScanJobSnapshotStats
    diagnostic_summary: ScanJobDiagnosticSummary
    recent_failure_samples: list[ScanJobSnapshotSample] = Field(default_factory=list)
    recent_401_samples: list[ScanJobSnapshotSample] = Field(default_factory=list)
    recent_quota_samples: list[ScanJobSnapshotSample] = Field(default_factory=list)
