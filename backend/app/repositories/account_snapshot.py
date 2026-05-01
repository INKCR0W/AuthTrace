from __future__ import annotations

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
