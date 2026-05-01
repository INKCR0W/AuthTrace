from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.repositories.scan_job import ScanJobListFilters, get_scan_job, list_scan_jobs
from app.schemas.scan_job import ScanJobDetailResponse, ScanJobListResponse, ScanJobSummary


router = APIRouter()


@router.get("", response_model=ScanJobListResponse)
def get_scan_jobs(
    db: Session = Depends(get_db_session),
    source_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    trigger_mode: str | None = Query(default=None),
    started_from: datetime | None = Query(default=None),
    started_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ScanJobListResponse:
    items, total = list_scan_jobs(
        db,
        filters=ScanJobListFilters(
            source_id=source_id,
            status=status_filter,
            trigger_mode=trigger_mode,
            started_from=started_from,
            started_to=started_to,
            limit=limit,
            offset=offset,
        ),
    )
    return ScanJobListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[ScanJobSummary.model_validate(item) for item in items],
    )


@router.get("/{scan_job_id}", response_model=ScanJobDetailResponse)
def get_scan_job_detail(
    scan_job_id: int,
    db: Session = Depends(get_db_session),
) -> ScanJobDetailResponse:
    scan_job = get_scan_job(db, scan_job_id=scan_job_id)
    if scan_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="扫描任务不存在")

    return ScanJobDetailResponse(item=ScanJobSummary.model_validate(scan_job))
