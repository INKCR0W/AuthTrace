from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db_session
from app.core.config import Settings
from app.repositories.management_source import ensure_default_management_source
from app.schemas.management_source import DefaultManagementSourceResponse
from app.services.scan_scheduler import AuthFileScanScheduler, build_scheduler_status_snapshot


router = APIRouter()


def _serialize_datetime(value: object) -> str | None:
    if not hasattr(value, "isoformat"):
        return None
    serialized = value.isoformat()
    return serialized.replace("+00:00", "Z")


def _build_scheduler_payload(request: Request, settings: Settings) -> dict[str, object]:
    scheduler = getattr(request.app.state, "auth_file_scan_scheduler", None)
    if isinstance(scheduler, AuthFileScanScheduler):
        snapshot = scheduler.get_status_snapshot()
    else:
        snapshot = build_scheduler_status_snapshot(settings)

    return {
        "scheduler_enabled": snapshot.enabled,
        "scheduler_running": snapshot.running,
        "scheduler_interval_minutes": snapshot.interval_minutes,
        "scheduler_jitter_seconds": snapshot.jitter_seconds,
        "scheduler_next_run_at": _serialize_datetime(snapshot.next_run_at),
        "scheduler_last_started_at": _serialize_datetime(snapshot.last_started_at),
        "scheduler_last_finished_at": _serialize_datetime(snapshot.last_finished_at),
        "scheduler_last_status": snapshot.last_status,
        "scheduler_last_error_message": snapshot.last_error_message,
    }


@router.get("/default", response_model=DefaultManagementSourceResponse)
def get_default_management_source(
    request: Request,
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
            **_build_scheduler_payload(request, settings),
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
        **_build_scheduler_payload(request, settings),
    )
