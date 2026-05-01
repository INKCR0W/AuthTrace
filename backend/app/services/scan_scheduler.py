from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.clients.management import ManagementApiClient
from app.core.config import Settings
from app.core.database import SessionLocal
from app.services.auth_file_sync import ScanJobAlreadyRunningError, run_auth_file_sync


logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class SchedulerStatusSnapshot:
    enabled: bool
    running: bool
    interval_minutes: int
    next_run_at: datetime | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_status: str | None = None
    last_error_message: str | None = None


def build_scheduler_status_snapshot(settings: Settings) -> SchedulerStatusSnapshot:
    snapshot = SchedulerStatusSnapshot(
        enabled=settings.scheduler_enabled,
        running=False,
        interval_minutes=settings.scheduler_interval_minutes,
    )
    if settings.scheduler_enabled and not settings.management_is_configured:
        snapshot.last_status = "blocked"
        snapshot.last_error_message = "management source 配置不完整，自动扫描未启动"
    return snapshot


class AuthFileScanScheduler:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: Callable[[], Session] = SessionLocal,
        client_factory: Callable[[Settings], ManagementApiClient] = ManagementApiClient.from_settings,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.client_factory = client_factory
        self.scheduler = AsyncIOScheduler(timezone=settings.timezone)
        self.job_id = "authtrace_auth_file_scan"
        self.status = build_scheduler_status_snapshot(settings)

    def start(self) -> None:
        if not self.settings.scheduler_enabled:
            return
        if self.scheduler.running:
            self._refresh_next_run_at()
            return
        if not self.settings.management_is_configured:
            logger.warning("自动扫描未启动：management source 配置不完整")
            return

        self.scheduler.add_job(
            self.run_once,
            trigger="interval",
            minutes=self.settings.scheduler_interval_minutes,
            id=self.job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=60,
        )
        self.scheduler.start()
        self.status.running = True
        self.status.last_error_message = None
        self._refresh_next_run_at()
        logger.info("自动扫描已启动，间隔 %s 分钟", self.settings.scheduler_interval_minutes)

    def shutdown(self) -> None:
        if not self.scheduler.running:
            self.status.running = False
            self.status.next_run_at = None
            return

        self.scheduler.shutdown(wait=False)
        self.status.running = False
        self.status.next_run_at = None
        logger.info("自动扫描已停止")

    def get_status_snapshot(self) -> SchedulerStatusSnapshot:
        self._refresh_next_run_at()
        return SchedulerStatusSnapshot(
            enabled=self.status.enabled,
            running=self.status.running,
            interval_minutes=self.status.interval_minutes,
            next_run_at=self.status.next_run_at,
            last_started_at=self.status.last_started_at,
            last_finished_at=self.status.last_finished_at,
            last_status=self.status.last_status,
            last_error_message=self.status.last_error_message,
        )

    async def run_once(self) -> None:
        self.status.last_started_at = _utcnow()
        self.status.last_finished_at = None
        self.status.last_status = "running"
        self.status.last_error_message = None

        try:
            client = self.client_factory(self.settings)
            with self.session_factory() as db:
                result = await run_auth_file_sync(
                    db,
                    settings=self.settings,
                    client=client,
                    trigger_mode="scheduler",
                )
            self.status.last_status = result.status
        except ScanJobAlreadyRunningError as exc:
            self.status.last_status = "skipped_conflict"
            self.status.last_error_message = f"已有运行中的扫描任务 #{exc.scan_job_id}"
            logger.info("自动扫描跳过：已有运行中的扫描任务 #%s", exc.scan_job_id)
        except Exception as exc:
            self.status.last_status = "failed"
            self.status.last_error_message = str(exc)
            logger.exception("自动扫描执行失败")
        finally:
            self.status.last_finished_at = _utcnow()
            self._refresh_next_run_at()

    def _refresh_next_run_at(self) -> None:
        self.status.running = self.scheduler.running
        if not self.scheduler.running:
            self.status.next_run_at = None
            return

        job = self.scheduler.get_job(self.job_id)
        self.status.next_run_at = None if job is None else job.next_run_time
