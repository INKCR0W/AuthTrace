from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("source_id", "auth_index", name="source_auth_index"),
        CheckConstraint(
            "current_weekly_used_percent is null or current_weekly_used_percent between 0 and 100",
            name="current_weekly_pct",
        ),
        CheckConstraint(
            "current_short_used_percent is null or current_short_used_percent between 0 and 100",
            name="current_short_pct",
        ),
        Index("ix_accounts_provider_account_type", "provider", "account_type"),
        Index("ix_accounts_current_is_401_current_last_checked_at", "current_is_401", "current_last_checked_at"),
        Index(
            "ix_accounts_current_invalid_quota_current_last_checked_at",
            "current_invalid_quota",
            "current_last_checked_at",
        ),
        Index("ix_accounts_disabled_current_last_checked_at", "disabled", "current_last_checked_at"),
        Index("ix_accounts_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("management_sources.id"), nullable=False)
    auth_index: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chatgpt_account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    upstream_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    current_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_is_401: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    current_invalid_quota: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    current_weekly_used_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    current_weekly_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_short_used_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    current_short_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_remaining: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    current_limit_reached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    current_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    current_last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    source_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source = relationship("ManagementSource", back_populates="accounts")
    snapshots = relationship("AccountSnapshot", back_populates="account")
    events = relationship("AccountEvent", back_populates="account")
