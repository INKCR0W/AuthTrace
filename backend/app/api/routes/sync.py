from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db_session, get_management_client
from app.clients.management import ManagementApiClient
from app.core.config import Settings
from app.schemas.sync import AuthFileSyncRequest, AuthFileSyncResponse
from app.services.auth_file_sync import ScanJobAlreadyRunningError, run_auth_file_sync


router = APIRouter()


def _serialize_datetime(value: object) -> str | None:
    if not hasattr(value, "isoformat"):
        return None
    serialized = value.isoformat()
    return serialized.replace("+00:00", "Z")


@router.post("/auth-files", response_model=AuthFileSyncResponse)
async def sync_auth_files(
    payload: AuthFileSyncRequest = Body(default_factory=AuthFileSyncRequest),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
    client: ManagementApiClient = Depends(get_management_client),
) -> AuthFileSyncResponse:
    try:
        return await run_auth_file_sync(
            db,
            settings=settings,
            client=client,
            trigger_mode=payload.trigger_mode,
        )
    except ScanJobAlreadyRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "当前已有进行中的扫描任务",
                "running_scan_job_id": exc.scan_job_id,
                "source_id": exc.source_id,
                "scan_started_at": _serialize_datetime(exc.scan_started_at),
            },
        ) from exc
