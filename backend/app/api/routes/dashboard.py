from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.serializers import serialize_latest_scan_job_summary
from app.api.deps import get_db_session
from app.repositories.dashboard import get_overview_stats
from app.schemas.dashboard import (
    DashboardOverviewResponse,
    DimensionBreakdownItem,
    OverviewTrendPoint,
)


router = APIRouter()


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(
    db: Session = Depends(get_db_session),
) -> DashboardOverviewResponse:
    overview = get_overview_stats(db)
    return DashboardOverviewResponse(
        total_accounts=overview.total_accounts,
        active_accounts=overview.active_accounts,
        disabled_accounts=overview.disabled_accounts,
        deleted_accounts=overview.deleted_accounts,
        current_401_accounts=overview.current_401_accounts,
        current_invalid_quota_accounts=overview.current_invalid_quota_accounts,
        new_401_events_last_24h=overview.new_401_events_last_24h,
        new_quota_events_last_24h=overview.new_quota_events_last_24h,
        recent_401_trend=[
            OverviewTrendPoint(
                bucket_start=point.bucket_start,
                became_401_count=point.became_401_count,
            )
            for point in overview.recent_401_trend
        ],
        provider_breakdown=[
            DimensionBreakdownItem.model_validate(item)
            for item in overview.provider_breakdown
        ],
        account_type_breakdown=[
            DimensionBreakdownItem.model_validate(item)
            for item in overview.account_type_breakdown
        ],
        latest_scan_job=(
            serialize_latest_scan_job_summary(overview.latest_scan_job)
            if overview.latest_scan_job is not None
            else None
        ),
    )
