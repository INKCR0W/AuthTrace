from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.account import AccountEventSummary, AccountSnapshotSummary, AccountSummary


class EventListItem(BaseModel):
    event: AccountEventSummary
    account: AccountSummary
    related_snapshot: AccountSnapshotSummary
    previous_snapshot: AccountSnapshotSummary | None = None


class EventListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[EventListItem] = Field(default_factory=list)


class EventDetailResponse(BaseModel):
    item: EventListItem
    context_snapshots: list[AccountSnapshotSummary] = Field(default_factory=list)
    context_events: list[AccountEventSummary] = Field(default_factory=list)
