from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.account_snapshot import AccountSnapshot
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


@dataclass(slots=True)
class ScanJobSnapshotStats:
    total_snapshots: int
    success_snapshots: int
    partial_failed_snapshots: int
    failed_snapshots: int
    is_401_snapshots: int
    invalid_quota_snapshots: int


@dataclass(slots=True)
class ScanJobSnapshotSampleRow:
    snapshot: AccountSnapshot
    account: Account


@dataclass(slots=True)
class ScanJobDetail:
    scan_job: ScanJob
    snapshot_stats: ScanJobSnapshotStats
    recent_failure_samples: list[ScanJobSnapshotSampleRow]
    recent_401_samples: list[ScanJobSnapshotSampleRow]
    recent_quota_samples: list[ScanJobSnapshotSampleRow]


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


def get_scan_job_detail(
    db: Session,
    *,
    scan_job_id: int,
    sample_limit: int = 5,
) -> ScanJobDetail | None:
    scan_job = db.get(ScanJob, scan_job_id)
    if scan_job is None:
        return None

    stats_row = db.execute(
        select(
            func.count(AccountSnapshot.id),
            func.sum(case((AccountSnapshot.snapshot_status == "success", 1), else_=0)),
            func.sum(case((AccountSnapshot.snapshot_status == "partial_failed", 1), else_=0)),
            func.sum(case((AccountSnapshot.snapshot_status == "failed", 1), else_=0)),
            func.sum(case((AccountSnapshot.is_401.is_(True), 1), else_=0)),
            func.sum(case((AccountSnapshot.invalid_quota.is_(True), 1), else_=0)),
        ).where(AccountSnapshot.scan_job_id == scan_job_id)
    ).one()

    snapshot_stats = ScanJobSnapshotStats(
        total_snapshots=int(stats_row[0] or 0),
        success_snapshots=int(stats_row[1] or 0),
        partial_failed_snapshots=int(stats_row[2] or 0),
        failed_snapshots=int(stats_row[3] or 0),
        is_401_snapshots=int(stats_row[4] or 0),
        invalid_quota_snapshots=int(stats_row[5] or 0),
    )

    return ScanJobDetail(
        scan_job=scan_job,
        snapshot_stats=snapshot_stats,
        recent_failure_samples=_list_snapshot_samples(
            db,
            scan_job_id=scan_job_id,
            sample_limit=sample_limit,
            filter_expression=AccountSnapshot.snapshot_status.in_(("partial_failed", "failed")),
        ),
        recent_401_samples=_list_snapshot_samples(
            db,
            scan_job_id=scan_job_id,
            sample_limit=sample_limit,
            filter_expression=AccountSnapshot.is_401.is_(True),
        ),
        recent_quota_samples=_list_snapshot_samples(
            db,
            scan_job_id=scan_job_id,
            sample_limit=sample_limit,
            filter_expression=AccountSnapshot.invalid_quota.is_(True),
        ),
    )


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


def _list_snapshot_samples(
    db: Session,
    *,
    scan_job_id: int,
    sample_limit: int,
    filter_expression: object,
) -> list[ScanJobSnapshotSampleRow]:
    rows = db.execute(
        select(AccountSnapshot, Account)
        .join(Account, Account.id == AccountSnapshot.account_id)
        .where(AccountSnapshot.scan_job_id == scan_job_id, filter_expression)
        .order_by(AccountSnapshot.checked_at.desc(), AccountSnapshot.id.desc())
        .limit(sample_limit)
    ).all()
    return [ScanJobSnapshotSampleRow(snapshot=snapshot, account=account) for snapshot, account in rows]
