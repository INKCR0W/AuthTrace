from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ScanJob(TimestampMixin, Base):
    __tablename__ = "scan_jobs"
    __table_args__ = (
        Index("ix_scan_jobs_source_id_scan_started_at", "source_id", "scan_started_at"),
        Index("ix_scan_jobs_status_scan_started_at", "status", "scan_started_at"),
        Index(
            "uq_scan_jobs_source_id_running",
            "source_id",
            unique=True,
            sqlite_where=text("status = 'running'"),
            postgresql_where=text("status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("management_sources.id"), nullable=False)
    trigger_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    scan_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scan_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    eligible_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    scanned_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    success_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    failed_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    new_401_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    new_quota_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)

    source = relationship("ManagementSource", back_populates="scan_jobs")
    snapshots = relationship("AccountSnapshot", back_populates="scan_job")
