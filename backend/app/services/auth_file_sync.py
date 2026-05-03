from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clients.management import ManagementApiClient
from app.core.config import Settings
from app.models.account import Account
from app.models.account_event import AccountEvent
from app.models.account_snapshot import AccountSnapshot
from app.models.scan_job import ScanJob
from app.repositories.account_snapshot import get_latest_snapshot_for_account
from app.repositories.account import AuthFileSyncResult, SyncedAuthFile, sync_accounts_from_auth_files
from app.repositories.management_source import ensure_default_management_source
from app.repositories.scan_job import create_scan_job, get_running_scan_job
from app.schemas.sync import AuthFileSyncResponse
from app.services.usage_probe import UsageProbeParseResult, parse_usage_probe_response


@dataclass(slots=True)
class UsageScanStats:
    scanned_accounts: int
    success_accounts: int
    failed_accounts: int
    new_401_events: int
    new_quota_events: int


@dataclass(slots=True)
class ProbeExecutionResult:
    synced: SyncedAuthFile
    checked_at: datetime
    result: UsageProbeParseResult


class ScanJobAlreadyRunningError(RuntimeError):
    def __init__(self, scan_job: ScanJob) -> None:
        super().__init__("scan job already running")
        self.scan_job_id = scan_job.id
        self.source_id = scan_job.source_id
        self.scan_started_at = scan_job.scan_started_at


def describe_exception(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return f"{exc.__class__.__name__}（未提供错误详情）"


async def run_auth_file_sync(
    db: Session,
    *,
    settings: Settings,
    client: ManagementApiClient,
    trigger_mode: str = "manual",
) -> AuthFileSyncResponse:
    source = ensure_default_management_source(db, settings)
    running_scan_job = get_running_scan_job(db, source_id=source.id)
    if running_scan_job is not None:
        raise ScanJobAlreadyRunningError(running_scan_job)

    started_at = _utcnow()
    try:
        scan_job = create_scan_job(
            db,
            source_id=source.id,
            trigger_mode=trigger_mode,
            started_at=started_at,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        running_scan_job = get_running_scan_job(db, source_id=source.id)
        if running_scan_job is not None:
            raise ScanJobAlreadyRunningError(running_scan_job) from exc
        raise

    scan_job_id = scan_job.id

    try:
        await client.refresh_config()
        auth_files = await client.list_auth_files()
        sync_result = sync_accounts_from_auth_files(
            db,
            source_id=source.id,
            auth_files=auth_files,
            seen_at=started_at,
            settings=settings,
        )
        persisted_scan_job = db.get(ScanJob, scan_job_id)
        if persisted_scan_job is None:
            raise RuntimeError("scan job not found after account sync")
        _mark_scan_job_accounts_synced(
            persisted_scan_job,
            started_at=started_at,
            sync_result=sync_result,
        )
        db.commit()

        usage_scan_stats = await _scan_usage_for_eligible_accounts(
            db,
            client=client,
            synced_auth_files=sync_result.eligible_auth_files,
            scan_job_id=scan_job_id,
            started_at=started_at,
            settings=settings,
        )
        persisted_scan_job = db.get(ScanJob, scan_job_id)
        if persisted_scan_job is None:
            raise RuntimeError("scan job not found after creation")
        _mark_scan_job_success(
            persisted_scan_job,
            started_at=started_at,
            sync_result=sync_result,
            usage_scan_stats=usage_scan_stats,
        )
        db.commit()
        return AuthFileSyncResponse(
            scan_job_id=persisted_scan_job.id,
            source_id=source.id,
            source_key=source.source_key,
            status=persisted_scan_job.status,
            total_accounts=sync_result.total_accounts,
            synced_accounts=sync_result.synced_accounts,
            eligible_accounts=sync_result.eligible_accounts,
            skipped_accounts=sync_result.skipped_accounts,
            missing_auth_index_accounts=sync_result.missing_auth_index_accounts,
            scanned_accounts=usage_scan_stats.scanned_accounts,
            successful_snapshots=usage_scan_stats.success_accounts,
            failed_snapshots=usage_scan_stats.failed_accounts,
        )
    except Exception as exc:
        db.rollback()
        failed_scan_job = db.get(ScanJob, scan_job_id)
        if failed_scan_job is not None:
            finished_at = _utcnow()
            failed_scan_job.status = "failed"
            failed_scan_job.scan_finished_at = finished_at
            failed_scan_job.duration_ms = _duration_ms(started_at=started_at, finished_at=finished_at)
            failed_scan_job.error_message = describe_exception(exc)
            db.commit()
        raise


def _mark_scan_job_accounts_synced(
    scan_job: ScanJob,
    *,
    started_at: datetime,
    sync_result: AuthFileSyncResult,
) -> None:
    finished_at = _utcnow()
    scan_job.total_accounts = sync_result.total_accounts
    scan_job.eligible_accounts = sync_result.eligible_accounts
    scan_job.duration_ms = _duration_ms(started_at=started_at, finished_at=finished_at)


def _mark_scan_job_success(
    scan_job: ScanJob,
    *,
    started_at: datetime,
    sync_result: AuthFileSyncResult,
    usage_scan_stats: UsageScanStats,
) -> None:
    finished_at = _utcnow()
    scan_job.status = "partial_failed" if usage_scan_stats.failed_accounts > 0 else "success"
    scan_job.scan_finished_at = finished_at
    scan_job.total_accounts = sync_result.total_accounts
    scan_job.eligible_accounts = sync_result.eligible_accounts
    scan_job.scanned_accounts = usage_scan_stats.scanned_accounts
    scan_job.success_accounts = usage_scan_stats.success_accounts
    scan_job.failed_accounts = usage_scan_stats.failed_accounts
    scan_job.new_401_events = usage_scan_stats.new_401_events
    scan_job.new_quota_events = usage_scan_stats.new_quota_events
    scan_job.duration_ms = _duration_ms(started_at=started_at, finished_at=finished_at)
    scan_job.error_message = None


def _duration_ms(*, started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _scan_usage_for_eligible_accounts(
    db: Session,
    *,
    client: ManagementApiClient,
    synced_auth_files: list[SyncedAuthFile],
    scan_job_id: int,
    started_at: datetime,
    settings: Settings,
) -> UsageScanStats:
    scanned_accounts = 0
    success_accounts = 0
    failed_accounts = 0
    new_401_events = 0
    new_quota_events = 0

    weekly_threshold = Decimal(str(settings.management_weekly_quota_threshold))
    short_threshold = Decimal(str(settings.management_short_quota_threshold))
    async for probe_result in _iter_probe_eligible_accounts(
        client=client,
        synced_auth_files=synced_auth_files,
        weekly_threshold=weekly_threshold,
        short_threshold=short_threshold,
        concurrency=settings.management_probe_concurrency,
        delay_min_seconds=settings.management_probe_delay_min_seconds,
        delay_max_seconds=settings.management_probe_delay_max_seconds,
    ):
        scanned_accounts += 1
        synced = probe_result.synced
        checked_at = probe_result.checked_at
        result = probe_result.result
        previous_snapshot = get_latest_snapshot_for_account(db, account_id=synced.account.id)
        snapshot = AccountSnapshot(
            account_id=synced.account.id,
            scan_job_id=scan_job_id,
            checked_at=checked_at,
            snapshot_status=result.snapshot_status,
            probe_status_code=result.probe_status_code,
            is_401=result.is_401,
            quota_status_code=result.quota_status_code,
            invalid_quota=result.invalid_quota,
            quota_source=result.quota_source,
            weekly_used_percent=result.weekly_used_percent,
            weekly_reset_at=result.weekly_reset_at,
            short_used_percent=result.short_used_percent,
            short_reset_at=result.short_reset_at,
            remaining=result.remaining,
            limit_reached=result.limit_reached,
            allowed=result.allowed,
            status_message=_stringify_text_value(synced.auth_file.get("status_message")),
            raw_auth_file_json=synced.auth_file,
            raw_usage_json=result.raw_usage_json,
            error_message=result.error_message,
            created_at=checked_at,
        )
        db.add(snapshot)
        db.flush()

        if result.snapshot_status != "success":
            failed_accounts += 1
        else:
            event_stats = _create_events_for_snapshot(
                db,
                account=synced.account,
                previous_snapshot=previous_snapshot,
                current_snapshot=snapshot,
            )
            new_401_events += event_stats.new_401_events
            new_quota_events += event_stats.new_quota_events

            success_accounts += 1
            _apply_current_state_from_probe_result(
                synced.account,
                result=result,
                checked_at=checked_at,
            )

        _mark_scan_job_usage_progress(
            db,
            scan_job_id=scan_job_id,
            started_at=started_at,
            scanned_accounts=scanned_accounts,
            success_accounts=success_accounts,
            failed_accounts=failed_accounts,
            new_401_events=new_401_events,
            new_quota_events=new_quota_events,
        )
        db.commit()

    db.flush()
    return UsageScanStats(
        scanned_accounts=scanned_accounts,
        success_accounts=success_accounts,
        failed_accounts=failed_accounts,
        new_401_events=new_401_events,
        new_quota_events=new_quota_events,
    )


def _mark_scan_job_usage_progress(
    db: Session,
    *,
    scan_job_id: int,
    started_at: datetime,
    scanned_accounts: int,
    success_accounts: int,
    failed_accounts: int,
    new_401_events: int,
    new_quota_events: int,
) -> None:
    scan_job = db.get(ScanJob, scan_job_id)
    if scan_job is None:
        raise RuntimeError("scan job not found while updating usage progress")
    finished_at = _utcnow()
    scan_job.scanned_accounts = scanned_accounts
    scan_job.success_accounts = success_accounts
    scan_job.failed_accounts = failed_accounts
    scan_job.new_401_events = new_401_events
    scan_job.new_quota_events = new_quota_events
    scan_job.duration_ms = _duration_ms(started_at=started_at, finished_at=finished_at)


async def _iter_probe_eligible_accounts(
    *,
    client: ManagementApiClient,
    synced_auth_files: list[SyncedAuthFile],
    weekly_threshold: Decimal,
    short_threshold: Decimal,
    concurrency: int,
    delay_min_seconds: float,
    delay_max_seconds: float,
) -> AsyncIterator[ProbeExecutionResult]:
    semaphore = asyncio.Semaphore(concurrency)

    async def _run_probe(synced: SyncedAuthFile) -> ProbeExecutionResult:
        async with semaphore:
            if delay_max_seconds > 0:
                await asyncio.sleep(random.uniform(delay_min_seconds, delay_max_seconds))
            checked_at = _utcnow()
            result = await _probe_account_usage(
                client,
                synced=synced,
                weekly_threshold=weekly_threshold,
                short_threshold=short_threshold,
            )
        return ProbeExecutionResult(
            synced=synced,
            checked_at=checked_at,
            result=result,
        )

    tasks = [asyncio.create_task(_run_probe(synced)) for synced in synced_auth_files]
    for task in asyncio.as_completed(tasks):
        yield await task


async def _probe_account_usage(
    client: ManagementApiClient,
    *,
    synced: SyncedAuthFile,
    weekly_threshold: Decimal,
    short_threshold: Decimal,
) -> UsageProbeParseResult:
    try:
        response = await client.probe_usage(
            auth_index=synced.account.auth_index,
            chatgpt_account_id=synced.account.chatgpt_account_id,
        )
    except Exception as exc:
        return UsageProbeParseResult(
            snapshot_status="failed",
            probe_status_code=None,
            is_401=False,
            quota_status_code=None,
            invalid_quota=False,
            quota_source=None,
            weekly_used_percent=None,
            weekly_reset_at=None,
            short_used_percent=None,
            short_reset_at=None,
            remaining=None,
            limit_reached=None,
            allowed=None,
            raw_usage_json=None,
            error_message=describe_exception(exc),
            has_quota_observation=False,
        )

    return parse_usage_probe_response(
        response,
        status_message=synced.auth_file.get("status_message"),
        weekly_quota_threshold=weekly_threshold,
        short_quota_threshold=short_threshold,
    )


def _apply_current_state_from_probe_result(
    account: Account,
    *,
    result: UsageProbeParseResult,
    checked_at: datetime,
) -> None:
    if result.snapshot_status != "success" or result.probe_status_code is None:
        return

    account.current_status_code = result.probe_status_code
    account.current_is_401 = result.is_401
    account.current_last_checked_at = checked_at

    if not result.has_quota_observation:
        if result.snapshot_status == "success":
            _clear_current_quota_state(account)
        return

    account.current_invalid_quota = result.invalid_quota
    account.current_weekly_used_percent = result.weekly_used_percent
    account.current_weekly_reset_at = result.weekly_reset_at
    account.current_short_used_percent = result.short_used_percent
    account.current_short_reset_at = result.short_reset_at
    account.current_remaining = result.remaining
    account.current_limit_reached = result.limit_reached
    account.current_allowed = result.allowed


def _clear_current_quota_state(account: Account) -> None:
    account.current_invalid_quota = False
    account.current_weekly_used_percent = None
    account.current_weekly_reset_at = None
    account.current_short_used_percent = None
    account.current_short_reset_at = None
    account.current_remaining = None
    account.current_limit_reached = None
    account.current_allowed = None


def _stringify_text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return json.dumps(value, ensure_ascii=False)


@dataclass(slots=True)
class EventGenerationStats:
    new_401_events: int = 0
    new_quota_events: int = 0


def _create_events_for_snapshot(
    db: Session,
    *,
    account: Account,
    previous_snapshot: AccountSnapshot | None,
    current_snapshot: AccountSnapshot,
) -> EventGenerationStats:
    if previous_snapshot is None:
        return EventGenerationStats()
    if current_snapshot.snapshot_status != "success":
        return EventGenerationStats()

    stats = EventGenerationStats()
    for event in _build_transition_events(
        account=account,
        previous_snapshot=previous_snapshot,
        current_snapshot=current_snapshot,
    ):
        db.add(event)
        if event.event_type == "became_401":
            stats.new_401_events += 1
    return stats


def _build_transition_events(
    *,
    account: Account,
    previous_snapshot: AccountSnapshot,
    current_snapshot: AccountSnapshot,
) -> list[AccountEvent]:
    events: list[AccountEvent] = []

    if not previous_snapshot.is_401 and current_snapshot.is_401:
        events.append(
            _new_event(
                account=account,
                event_type="became_401",
                previous_snapshot=previous_snapshot,
                current_snapshot=current_snapshot,
            )
        )
    elif previous_snapshot.is_401 and not current_snapshot.is_401:
        events.append(
            _new_event(
                account=account,
                event_type="recovered_from_401",
                previous_snapshot=previous_snapshot,
                current_snapshot=current_snapshot,
            )
        )

    previous_disabled = _extract_disabled_flag(previous_snapshot)
    current_disabled = _extract_disabled_flag(current_snapshot)
    if previous_disabled is not None and current_disabled is not None and previous_disabled != current_disabled:
        events.append(
            _new_event(
                account=account,
                event_type="disabled_changed",
                previous_snapshot=previous_snapshot,
                current_snapshot=current_snapshot,
            )
        )

    return events


def _new_event(
    *,
    account: Account,
    event_type: str,
    previous_snapshot: AccountSnapshot,
    current_snapshot: AccountSnapshot,
) -> AccountEvent:
    return AccountEvent(
        account_id=account.id,
        event_type=event_type,
        event_time=current_snapshot.checked_at,
        related_snapshot_id=current_snapshot.id,
        previous_snapshot_id=previous_snapshot.id,
        from_status_code=previous_snapshot.probe_status_code,
        to_status_code=current_snapshot.probe_status_code,
        from_is_401=previous_snapshot.is_401,
        to_is_401=current_snapshot.is_401,
        from_invalid_quota=previous_snapshot.invalid_quota,
        to_invalid_quota=current_snapshot.invalid_quota,
        from_disabled=_extract_disabled_flag(previous_snapshot),
        to_disabled=_extract_disabled_flag(current_snapshot),
        created_at=current_snapshot.checked_at,
    )


def _extract_disabled_flag(snapshot: AccountSnapshot) -> bool | None:
    raw_auth_file = snapshot.raw_auth_file_json
    if not isinstance(raw_auth_file, dict):
        return None
    disabled = raw_auth_file.get("disabled")
    if isinstance(disabled, bool):
        return disabled
    if disabled is None:
        return None
    text = str(disabled).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None
