from __future__ import annotations

from sqlalchemy import Boolean, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ManagementSource(TimestampMixin, Base):
    __tablename__ = "management_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    scan_jobs = relationship("ScanJob", back_populates="source")
    accounts = relationship("Account", back_populates="source")
