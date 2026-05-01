from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.scan_job import ScanJob


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
