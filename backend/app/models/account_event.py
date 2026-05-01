from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AccountEvent(Base):
    __tablename__ = "account_events"
    __table_args__ = (
        UniqueConstraint("account_id", "event_type", "related_snapshot_id", name="unique_transition"),
        Index("ix_account_events_account_id_event_time", "account_id", "event_time"),
        Index("ix_account_events_event_type_event_time", "event_type", "event_time"),
        Index("ix_account_events_related_snapshot_id", "related_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    related_snapshot_id: Mapped[int] = mapped_column(ForeignKey("account_snapshots.id"), nullable=False)
    previous_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_snapshots.id"), nullable=True
    )
    from_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_is_401: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    to_is_401: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    from_invalid_quota: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    to_invalid_quota: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    from_disabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    to_disabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    account = relationship("Account", back_populates="events")
    related_snapshot = relationship(
        "AccountSnapshot",
        back_populates="related_events",
        foreign_keys=[related_snapshot_id],
    )
    previous_snapshot = relationship(
        "AccountSnapshot",
        back_populates="previous_events",
        foreign_keys=[previous_snapshot_id],
    )
