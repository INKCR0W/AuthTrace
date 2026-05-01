from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.account import Account
from app.repositories.account import AccountListFilters, list_accounts as query_accounts
from app.repositories.account_event import list_recent_events_for_account
from app.repositories.account_snapshot import list_recent_snapshots_for_account
from app.schemas.account import (
    AccountDetailResponse,
    AccountEventSummary,
    AccountListResponse,
    AccountSnapshotSummary,
    AccountSummary,
)


router = APIRouter()


@router.get("", response_model=AccountListResponse)
def list_accounts(
    db: Session = Depends(get_db_session),
    provider: str | None = Query(default=None),
    account_type: str | None = Query(default=None),
    current_is_401: bool | None = Query(default=None),
    current_invalid_quota: bool | None = Query(default=None),
    disabled: bool | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    last_checked_from: datetime | None = Query(default=None),
    last_checked_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AccountListResponse:
    accounts, total = query_accounts(
        db,
        filters=AccountListFilters(
            provider=provider,
            account_type=account_type,
            current_is_401=current_is_401,
            current_invalid_quota=current_invalid_quota,
            disabled=disabled,
            include_deleted=include_deleted,
            last_checked_from=last_checked_from,
            last_checked_to=last_checked_to,
            limit=limit,
            offset=offset,
        ),
    )
    return AccountListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[AccountSummary.model_validate(account) for account in accounts],
    )


@router.get("/{account_id}", response_model=AccountDetailResponse)
def get_account_detail(
    account_id: int,
    db: Session = Depends(get_db_session),
    snapshot_limit: int = Query(default=20, ge=1, le=200),
    event_limit: int = Query(default=20, ge=1, le=200),
) -> AccountDetailResponse:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    snapshots = list_recent_snapshots_for_account(db, account_id=account_id, limit=snapshot_limit)
    events = list_recent_events_for_account(db, account_id=account_id, limit=event_limit)
    return AccountDetailResponse(
        account=AccountSummary.model_validate(account),
        recent_snapshots=[AccountSnapshotSummary.model_validate(item) for item in snapshots],
        recent_events=[AccountEventSummary.model_validate(item) for item in events],
    )
