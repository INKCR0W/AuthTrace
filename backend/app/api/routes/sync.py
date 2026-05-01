from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db_session, get_management_client
from app.clients.management import ManagementApiClient
from app.core.config import Settings
from app.schemas.sync import AuthFileSyncRequest, AuthFileSyncResponse
from app.services.auth_file_sync import run_auth_file_sync


router = APIRouter()


@router.post("/auth-files", response_model=AuthFileSyncResponse)
async def sync_auth_files(
    payload: AuthFileSyncRequest = Body(default_factory=AuthFileSyncRequest),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
    client: ManagementApiClient = Depends(get_management_client),
) -> AuthFileSyncResponse:
    return await run_auth_file_sync(
        db,
        settings=settings,
        client=client,
        trigger_mode=payload.trigger_mode,
    )
