from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.scan_job import ScanJob


@dataclass(slots=True)
class ScanJobListFilters:
    source_id: int | None = None
    status: str | None = None
    trigger_mode: str | None = None
    started_from: datetime | None = None
    started_to: datetime | None = None
    limit: int = 50
    offset: int = 0


def create_scan_job(
    db: Session,
    *,
    source_id: int,
    trigger_mode: str,
    started_at: datetime,
) -> ScanJob:
    scan_job = ScanJob(
        source_id=source_id,
        trigger_mode=trigger_mode,
        status="running",
        scan_started_at=started_at,
    )
    db.add(scan_job)
    db.flush()
    return scan_job


def get_running_scan_job(
    db: Session,
    *,
    source_id: int,
) -> ScanJob | None:
    statement = (
        select(ScanJob)
        .where(
            ScanJob.source_id == source_id,
            ScanJob.status == "running",
        )
        .order_by(ScanJob.scan_started_at.desc(), ScanJob.id.desc())
        .limit(1)
    )
    return db.scalar(statement)


def list_scan_jobs(
    db: Session,
    *,
    filters: ScanJobListFilters,
) -> tuple[list[ScanJob], int]:
    filtered_statement = _apply_scan_job_filters(select(ScanJob), filters=filters)
    count_statement = _apply_scan_job_filters(select(func.count(ScanJob.id)), filters=filters)

    items = list(
        db.scalars(
            filtered_statement
            .order_by(ScanJob.scan_started_at.desc(), ScanJob.id.desc())
            .offset(filters.offset)
            .limit(filters.limit)
        ).all()
    )
    total = int(db.scalar(count_statement) or 0)
    return items, total


def get_scan_job(
    db: Session,
    *,
    scan_job_id: int,
) -> ScanJob | None:
    return db.get(ScanJob, scan_job_id)


def _apply_scan_job_filters(statement: Select, *, filters: ScanJobListFilters) -> Select:
    if filters.source_id is not None:
        statement = statement.where(ScanJob.source_id == filters.source_id)
    if filters.status:
        statement = statement.where(ScanJob.status == filters.status)
    if filters.trigger_mode:
        statement = statement.where(ScanJob.trigger_mode == filters.trigger_mode)
    if filters.started_from is not None:
        statement = statement.where(ScanJob.scan_started_at >= filters.started_from)
    if filters.started_to is not None:
        statement = statement.where(ScanJob.scan_started_at <= filters.started_to)
    return statement
