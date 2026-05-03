from __future__ import annotations

from pydantic import BaseModel


class DefaultManagementSourceResponse(BaseModel):
    source_id: int | None = None
    source_key: str
    source_name: str
    base_url: str | None = None
    configured: bool
    is_enabled: bool
    target_type: str | None = None
    provider: str | None = None
    scheduler_enabled: bool
    scheduler_running: bool
    scheduler_interval_minutes: int
    scheduler_jitter_seconds: int
    scheduler_next_run_at: str | None = None
    scheduler_last_started_at: str | None = None
    scheduler_last_finished_at: str | None = None
    scheduler_last_status: str | None = None
    scheduler_last_error_message: str | None = None
