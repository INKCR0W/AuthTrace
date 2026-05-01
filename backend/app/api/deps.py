from __future__ import annotations

from typing import Generator

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.clients.management import ManagementApiClient, ManagementApiError
from app.core.config import Settings, get_settings
from app.core.database import get_db


def get_app_settings() -> Settings:
    return get_settings()


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_management_client(settings: Settings = Depends(get_app_settings)) -> ManagementApiClient:
    try:
        return ManagementApiClient.from_settings(settings)
    except ManagementApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="management source 配置不完整",
        ) from exc
