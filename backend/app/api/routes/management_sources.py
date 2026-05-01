from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db_session
from app.core.config import Settings
from app.repositories.management_source import ensure_default_management_source
from app.schemas.management_source import DefaultManagementSourceResponse


router = APIRouter()


@router.get("/default", response_model=DefaultManagementSourceResponse)
def get_default_management_source(
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> DefaultManagementSourceResponse:
    if not settings.management_base_url:
        return DefaultManagementSourceResponse(
            source_key=settings.management_source_key,
            source_name=settings.management_source_name,
            base_url=None,
            configured=False,
            is_enabled=False,
            target_type=settings.management_target_type,
            provider=settings.management_provider,
        )

    source = ensure_default_management_source(db, settings)
    db.commit()
    return DefaultManagementSourceResponse(
        source_id=source.id,
        source_key=source.source_key,
        source_name=source.source_name,
        base_url=source.base_url,
        configured=settings.management_is_configured,
        is_enabled=source.is_enabled,
        target_type=settings.management_target_type,
        provider=settings.management_provider,
    )
