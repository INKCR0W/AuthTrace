from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.management_source import ManagementSource


def ensure_default_management_source(db: Session, settings: Settings) -> ManagementSource:
    if not settings.management_base_url:
        raise ValueError("AUTHTRACE_MANAGEMENT_BASE_URL 未配置")

    source = db.scalar(
        select(ManagementSource).where(ManagementSource.source_key == settings.management_source_key)
    )
    if source is None:
        source = ManagementSource(
            source_key=settings.management_source_key,
            source_name=settings.management_source_name,
            base_url=settings.management_base_url,
            description=settings.management_source_description,
            is_enabled=True,
        )
        db.add(source)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            source = db.scalar(
                select(ManagementSource).where(ManagementSource.source_key == settings.management_source_key)
            )
            if source is None:
                raise
            source.source_name = settings.management_source_name
            source.base_url = settings.management_base_url
            source.description = settings.management_source_description
            source.is_enabled = True
            db.flush()
        return source

    source.source_name = settings.management_source_name
    source.base_url = settings.management_base_url
    source.description = settings.management_source_description
    source.is_enabled = True
    db.flush()
    return source
