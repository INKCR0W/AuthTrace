from __future__ import annotations

from pydantic import BaseModel, Field


class AuthFileSyncRequest(BaseModel):
    trigger_mode: str = Field(default="manual")


class AuthFileSyncResponse(BaseModel):
    scan_job_id: int
    source_id: int
    source_key: str
    status: str
    total_accounts: int
    synced_accounts: int
    eligible_accounts: int
    skipped_accounts: int
    missing_auth_index_accounts: int
    scanned_accounts: int
    successful_snapshots: int
    failed_snapshots: int
