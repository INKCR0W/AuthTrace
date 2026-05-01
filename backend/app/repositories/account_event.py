from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, aliased

from app.models.account import Account
from app.models.account_event import AccountEvent
from app.models.account_snapshot import AccountSnapshot


@dataclass(slots=True)
class EventListFilters:
    event_type: str | None = None
    account_id: int | None = None
    provider: str | None = None
    account_type: str | None = None
    current_is_401: bool | None = None
    event_time_from: datetime | None = None
    event_time_to: datetime | None = None
    limit: int = 50
    offset: int = 0


def list_events(
    db: Session,
    *,
    filters: EventListFilters,
) -> tuple[list[tuple[AccountEvent, Account, AccountSnapshot, AccountSnapshot | None]], int]:
    previous_snapshot = aliased(AccountSnapshot)
    filtered_statement = _apply_event_filters(
        _build_event_detail_statement(previous_snapshot=previous_snapshot),
        filters=filters,
    )
    count_statement = _apply_event_filters(select(func.count(AccountEvent.id)).join(Account), filters=filters)

    items = list(
        db.execute(
            filtered_statement.order_by(AccountEvent.event_time.desc(), AccountEvent.id.desc())
            .offset(filters.offset)
            .limit(filters.limit)
        ).all()
    )
    total = int(db.scalar(count_statement) or 0)
    return items, total


def get_event_detail(
    db: Session,
    *,
    event_id: int,
) -> tuple[AccountEvent, Account, AccountSnapshot, AccountSnapshot | None] | None:
    previous_snapshot = aliased(AccountSnapshot)
    statement = _build_event_detail_statement(previous_snapshot=previous_snapshot).where(
        AccountEvent.id == event_id
    )
    return db.execute(statement).one_or_none()


def list_recent_events_for_account(
    db: Session,
    *,
    account_id: int,
    limit: int,
) -> list[AccountEvent]:
    statement = (
        select(AccountEvent)
        .where(AccountEvent.account_id == account_id)
        .order_by(AccountEvent.event_time.desc(), AccountEvent.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def _build_event_detail_statement(
    *,
    previous_snapshot: AccountSnapshot,
) -> Select[tuple[AccountEvent, Account, AccountSnapshot, AccountSnapshot | None]]:
    return (
        select(AccountEvent, Account, AccountSnapshot, previous_snapshot)
        .join(Account, Account.id == AccountEvent.account_id)
        .join(AccountSnapshot, AccountSnapshot.id == AccountEvent.related_snapshot_id)
        .outerjoin(previous_snapshot, previous_snapshot.id == AccountEvent.previous_snapshot_id)
    )


def _apply_event_filters(statement: Select, *, filters: EventListFilters) -> Select:
    if filters.event_type:
        statement = statement.where(AccountEvent.event_type == filters.event_type)
    if filters.account_id is not None:
        statement = statement.where(AccountEvent.account_id == filters.account_id)
    if filters.provider:
        statement = statement.where(Account.provider == filters.provider)
    if filters.account_type:
        statement = statement.where(Account.account_type == filters.account_type)
    if filters.current_is_401 is not None:
        statement = statement.where(Account.current_is_401 == filters.current_is_401)
    if filters.event_time_from is not None:
        statement = statement.where(AccountEvent.event_time >= filters.event_time_from)
    if filters.event_time_to is not None:
        statement = statement.where(AccountEvent.event_time <= filters.event_time_to)
    return statement
