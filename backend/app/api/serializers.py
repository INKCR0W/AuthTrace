from __future__ import annotations

from app.schemas.dashboard import LatestScanJobSummary
from app.schemas.scan_job import ScanJobSnapshotSample, ScanJobSummary


LEGACY_BLANK_ERROR_MESSAGE = "未记录错误详情"


def normalize_error_message(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or LEGACY_BLANK_ERROR_MESSAGE


def serialize_scan_job_summary(scan_job: object) -> ScanJobSummary:
    summary = ScanJobSummary.model_validate(scan_job)
    summary.error_message = normalize_error_message(summary.error_message)
    return summary


def serialize_latest_scan_job_summary(scan_job: object) -> LatestScanJobSummary:
    summary = LatestScanJobSummary.model_validate(scan_job)
    summary.error_message = normalize_error_message(summary.error_message)
    return summary


def serialize_scan_job_snapshot_sample(sample: ScanJobSnapshotSample) -> ScanJobSnapshotSample:
    sample.error_message = normalize_error_message(sample.error_message)
    return sample
