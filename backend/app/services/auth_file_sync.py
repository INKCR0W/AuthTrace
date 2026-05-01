from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.clients.management import ManagementApiClient
from app.core.config import Settings
from app.models.scan_job import ScanJob
from app.repositories.account import AuthFileSyncStats, sync_accounts_from_auth_files
from app.repositories.management_source import ensure_default_management_source
from app.repositories.scan_job import create_scan_job
from app.schemas.sync import AuthFileSyncResponse


async def run_auth_file_sync(
    db: Session,
    *,
    settings: Settings,
    client: ManagementApiClient,
    trigger_mode: str = "manual",
) -> AuthFileSyncResponse:
    source = ensure_default_management_source(db, settings)
    started_at = _utcnow()
    scan_job = create_scan_job(
        db,
        source_id=source.id,
        trigger_mode=trigger_mode,
        started_at=started_at,
    )
    scan_job_id = scan_job.id
    db.commit()

    try:
        await client.refresh_config()
        auth_files = await client.list_auth_files()
        stats = sync_accounts_from_auth_files(
            db,
            source_id=source.id,
            auth_files=auth_files,
            seen_at=started_at,
            settings=settings,
        )
        persisted_scan_job = db.get(ScanJob, scan_job_id)
        if persisted_scan_job is None:
            raise RuntimeError("scan job not found after creation")
        _mark_scan_job_success(persisted_scan_job, started_at=started_at, stats=stats)
        db.commit()
        return AuthFileSyncResponse(
            scan_job_id=persisted_scan_job.id,
            source_id=source.id,
            source_key=source.source_key,
            status=persisted_scan_job.status,
            total_accounts=stats.total_accounts,
            synced_accounts=stats.synced_accounts,
            eligible_accounts=stats.eligible_accounts,
            skipped_accounts=stats.skipped_accounts,
            missing_auth_index_accounts=stats.missing_auth_index_accounts,
        )
    except Exception as exc:
        db.rollback()
        failed_scan_job = db.get(ScanJob, scan_job_id)
        if failed_scan_job is not None:
            finished_at = _utcnow()
            failed_scan_job.status = "failed"
            failed_scan_job.scan_finished_at = finished_at
            failed_scan_job.duration_ms = _duration_ms(started_at=started_at, finished_at=finished_at)
            failed_scan_job.error_message = str(exc)
            db.commit()
        raise


def _mark_scan_job_success(scan_job: ScanJob, *, started_at: datetime, stats: AuthFileSyncStats) -> None:
    finished_at = _utcnow()
    scan_job.status = "success"
    scan_job.scan_finished_at = finished_at
    scan_job.total_accounts = stats.total_accounts
    scan_job.eligible_accounts = stats.eligible_accounts
    scan_job.scanned_accounts = stats.synced_accounts
    scan_job.success_accounts = stats.synced_accounts
    scan_job.failed_accounts = stats.skipped_accounts
    scan_job.duration_ms = _duration_ms(started_at=started_at, finished_at=finished_at)
    scan_job.error_message = None


def _duration_ms(*, started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
