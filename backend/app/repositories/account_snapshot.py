from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account_snapshot import AccountSnapshot


def get_latest_snapshot_for_account(db: Session, *, account_id: int) -> AccountSnapshot | None:
    statement = (
        select(AccountSnapshot)
        .where(AccountSnapshot.account_id == account_id)
        .order_by(AccountSnapshot.checked_at.desc(), AccountSnapshot.id.desc())
        .limit(1)
    )
    return db.scalar(statement)


def list_recent_snapshots_for_account(
    db: Session,
    *,
    account_id: int,
    limit: int,
) -> list[AccountSnapshot]:
    statement = (
        select(AccountSnapshot)
        .where(AccountSnapshot.account_id == account_id)
        .order_by(AccountSnapshot.checked_at.desc(), AccountSnapshot.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def list_recent_snapshots_for_account_until(
    db: Session,
    *,
    account_id: int,
    checked_at_to: datetime,
    limit: int,
) -> list[AccountSnapshot]:
    statement = (
        select(AccountSnapshot)
        .where(
            AccountSnapshot.account_id == account_id,
            AccountSnapshot.checked_at <= checked_at_to,
        )
        .order_by(AccountSnapshot.checked_at.desc(), AccountSnapshot.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())
