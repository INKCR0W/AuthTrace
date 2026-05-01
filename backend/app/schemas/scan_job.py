from __future__ import annotations

from datetime import datetime

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


class ScanJobDetailResponse(BaseModel):
    item: ScanJobSummary
