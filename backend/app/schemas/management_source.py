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
