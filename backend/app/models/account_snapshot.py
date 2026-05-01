from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"
    __table_args__ = (
        CheckConstraint(
            "weekly_used_percent is null or weekly_used_percent between 0 and 100",
            name="weekly_pct",
        ),
        CheckConstraint(
            "short_used_percent is null or short_used_percent between 0 and 100",
            name="short_pct",
        ),
        Index("ix_account_snapshots_account_id_checked_at", "account_id", "checked_at"),
        Index("ix_account_snapshots_scan_job_id", "scan_job_id"),
        Index("ix_account_snapshots_checked_at", "checked_at"),
        Index(
            "ix_account_snapshots_checked_at_is_401_true",
            "checked_at",
            postgresql_where=text("is_401 = true"),
        ),
        Index(
            "ix_account_snapshots_checked_at_invalid_quota_true",
            "checked_at",
            postgresql_where=text("invalid_quota = true"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    scan_job_id: Mapped[int] = mapped_column(ForeignKey("scan_jobs.id"), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_status: Mapped[str] = mapped_column(String(32), nullable=False)
    probe_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_401: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    quota_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invalid_quota: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    quota_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    weekly_used_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    weekly_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    short_used_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    short_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remaining: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    limit_reached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    raw_auth_file_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    account = relationship("Account", back_populates="snapshots")
    scan_job = relationship("ScanJob", back_populates="snapshots")
    related_events = relationship(
        "AccountEvent",
        back_populates="related_snapshot",
        foreign_keys="AccountEvent.related_snapshot_id",
    )
    previous_events = relationship(
        "AccountEvent",
        back_populates="previous_snapshot",
        foreign_keys="AccountEvent.previous_snapshot_id",
    )
