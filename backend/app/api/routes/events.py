from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.repositories.account_event import EventListFilters, get_event_detail, list_events
from app.schemas.account import AccountEventSummary, AccountSnapshotSummary, AccountSummary
from app.schemas.event import EventDetailResponse, EventListItem, EventListResponse


router = APIRouter()


@router.get("", response_model=EventListResponse)
def get_events(
    db: Session = Depends(get_db_session),
    event_type: str | None = Query(default=None),
    account_id: int | None = Query(default=None),
    provider: str | None = Query(default=None),
    account_type: str | None = Query(default=None),
    current_is_401: bool | None = Query(default=None),
    event_time_from: datetime | None = Query(default=None),
    event_time_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EventListResponse:
    items, total = list_events(
        db,
        filters=EventListFilters(
            event_type=event_type,
            account_id=account_id,
            provider=provider,
            account_type=account_type,
            current_is_401=current_is_401,
            event_time_from=event_time_from,
            event_time_to=event_time_to,
            limit=limit,
            offset=offset,
        ),
    )
    return EventListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            EventListItem(
                event=AccountEventSummary.model_validate(event),
                account=AccountSummary.model_validate(account),
                related_snapshot=AccountSnapshotSummary.model_validate(related_snapshot),
                previous_snapshot=(
                    AccountSnapshotSummary.model_validate(previous_snapshot)
                    if previous_snapshot is not None
                    else None
                ),
            )
            for event, account, related_snapshot, previous_snapshot in items
        ],
    )


@router.get("/{event_id}", response_model=EventDetailResponse)
def get_event(
    event_id: int,
    db: Session = Depends(get_db_session),
) -> EventDetailResponse:
    result = get_event_detail(db, event_id=event_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="事件不存在")

    event, account, related_snapshot, previous_snapshot = result
    return EventDetailResponse(
        item=EventListItem(
            event=AccountEventSummary.model_validate(event),
            account=AccountSummary.model_validate(account),
            related_snapshot=AccountSnapshotSummary.model_validate(related_snapshot),
            previous_snapshot=(
                AccountSnapshotSummary.model_validate(previous_snapshot)
                if previous_snapshot is not None
                else None
            ),
        )
    )
