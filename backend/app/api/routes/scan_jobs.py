from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.repositories.scan_job import (
    ScanJobListFilters,
    ScanJobSnapshotSampleRow,
    get_scan_job_detail as fetch_scan_job_detail,
    list_scan_jobs,
)
from app.schemas.scan_job import (
    ScanJobAccountRef,
    ScanJobDetailResponse,
    ScanJobListResponse,
    ScanJobSnapshotSample,
    ScanJobSnapshotStats,
    ScanJobSummary,
)


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
    detail = fetch_scan_job_detail(db, scan_job_id=scan_job_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="扫描任务不存在")

    return ScanJobDetailResponse(
        item=ScanJobSummary.model_validate(detail.scan_job),
        snapshot_stats=ScanJobSnapshotStats.model_validate(detail.snapshot_stats),
        recent_failure_samples=[_serialize_snapshot_sample(item) for item in detail.recent_failure_samples],
        recent_401_samples=[_serialize_snapshot_sample(item) for item in detail.recent_401_samples],
        recent_quota_samples=[_serialize_snapshot_sample(item) for item in detail.recent_quota_samples],
    )


def _serialize_snapshot_sample(item: ScanJobSnapshotSampleRow) -> ScanJobSnapshotSample:
    snapshot = item.snapshot
    account = item.account
    return ScanJobSnapshotSample(
        id=snapshot.id,
        account_id=snapshot.account_id,
        scan_job_id=snapshot.scan_job_id,
        checked_at=snapshot.checked_at,
        snapshot_status=snapshot.snapshot_status,
        probe_status_code=snapshot.probe_status_code,
        is_401=snapshot.is_401,
        quota_status_code=snapshot.quota_status_code,
        invalid_quota=snapshot.invalid_quota,
        quota_source=snapshot.quota_source,
        weekly_used_percent=snapshot.weekly_used_percent,
        weekly_reset_at=snapshot.weekly_reset_at,
        short_used_percent=snapshot.short_used_percent,
        short_reset_at=snapshot.short_reset_at,
        remaining=snapshot.remaining,
        limit_reached=snapshot.limit_reached,
        allowed=snapshot.allowed,
        status_message=snapshot.status_message,
        raw_auth_file_json=snapshot.raw_auth_file_json,
        raw_usage_json=snapshot.raw_usage_json,
        error_message=snapshot.error_message,
        created_at=snapshot.created_at,
        account=ScanJobAccountRef(
            id=account.id,
            name=account.name,
            auth_index=account.auth_index,
            provider=account.provider,
            account_type=account.account_type,
            disabled=account.disabled,
        ),
    )
