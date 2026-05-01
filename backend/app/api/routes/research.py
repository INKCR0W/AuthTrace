from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.repositories.research import get_research_overview
from app.schemas.research import (
    ResearchBucketCount,
    ResearchCombinationBreakdownItem,
    ResearchEventSample,
    ResearchHourlyDistributionPoint,
    ResearchOverviewResponse,
    ResearchOverviewSummary,
    ResearchPre401Insights,
)


router = APIRouter()


@router.get("/overview", response_model=ResearchOverviewResponse)
def get_research_overview_api(
    db: Session = Depends(get_db_session),
    window_days: int = Query(default=7, ge=1, le=30),
) -> ResearchOverviewResponse:
    overview = get_research_overview(db, window_days=window_days)
    return ResearchOverviewResponse(
        window_days=overview.window_days,
        summary=ResearchOverviewSummary.model_validate(overview.summary),
        provider_account_type_breakdown=[
            ResearchCombinationBreakdownItem.model_validate(item)
            for item in overview.provider_account_type_breakdown
        ],
        event_hour_distribution=[
            ResearchHourlyDistributionPoint.model_validate(item)
            for item in overview.event_hour_distribution
        ],
        pre_401_insights=ResearchPre401Insights(
            sampled_events=overview.pre_401_insights.sampled_events,
            events_with_previous_snapshot=overview.pre_401_insights.events_with_previous_snapshot,
            weekly_used_percent_bands=[
                ResearchBucketCount.model_validate(item)
                for item in overview.pre_401_insights.weekly_used_percent_bands
            ],
            short_used_percent_bands=[
                ResearchBucketCount.model_validate(item)
                for item in overview.pre_401_insights.short_used_percent_bands
            ],
            signal_breakdown=[
                ResearchBucketCount.model_validate(item)
                for item in overview.pre_401_insights.signal_breakdown
            ],
            top_status_messages=[
                ResearchBucketCount.model_validate(item)
                for item in overview.pre_401_insights.top_status_messages
            ],
        ),
        recent_event_samples=[
            ResearchEventSample.model_validate(item)
            for item in overview.recent_event_samples
        ],
    )
