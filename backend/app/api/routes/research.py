from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.repositories.research import (
    RESEARCH_CURRENT_SIGNAL_COUNT_BUCKET_KEYS,
    RESEARCH_HISTORICAL_MATCH_LEVELS,
    RESEARCH_HISTORICAL_LIKE_EVENT_COUNT_BUCKET_KEYS,
    RESEARCH_PRE_401_GAP_BUCKET_KEYS,
    RESEARCH_SIGNAL_KEYS,
    get_research_overview,
    normalize_research_signal_pattern_key,
)
from app.schemas.research import (
    ResearchBucketCount,
    ResearchCombinationBreakdownItem,
    ResearchCurrentSignalBaseline,
    ResearchCurrentSignalGroupBreakdownItem,
    ResearchHistoricalReplayBreakdownItem,
    ResearchCurrentSignalSample,
    ResearchEventSample,
    ResearchHourlyDistributionPoint,
    ResearchOverviewResponse,
    ResearchOverviewSummary,
    ResearchPre401Insights,
    ResearchSignalComparisonItem,
    ResearchSignalPatternComparisonItem,
)


router = APIRouter()


@router.get("/overview", response_model=ResearchOverviewResponse)
def get_research_overview_api(
    db: Session = Depends(get_db_session),
    window_days: int = Query(default=7, ge=1, le=30),
    provider: str | None = Query(default=None),
    account_type: str | None = Query(default=None),
    current_signal_key: str | None = Query(default=None),
    current_status_message: str | None = Query(default=None),
    current_signal_pattern_key: str | None = Query(default=None),
    current_signal_count_bucket: str | None = Query(default=None),
    pre_401_signal_key: str | None = Query(default=None),
    pre_401_status_message: str | None = Query(default=None),
    pre_401_signal_pattern_key: str | None = Query(default=None),
    pre_401_gap_bucket: str | None = Query(default=None),
    current_match_level: str | None = Query(default=None),
    current_signal_min_streak: int | None = Query(default=None, ge=1, le=20),
    current_historical_like_bucket: str | None = Query(default=None),
    current_historical_gap_bucket: str | None = Query(default=None),
    current_historical_event_id: int | None = Query(default=None, ge=1),
) -> ResearchOverviewResponse:
    if current_signal_key is not None and current_signal_key not in RESEARCH_SIGNAL_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported current_signal_key: {current_signal_key}",
        )
    if pre_401_signal_key is not None and pre_401_signal_key not in RESEARCH_SIGNAL_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported pre_401_signal_key: {pre_401_signal_key}",
        )
    if (
        current_signal_count_bucket is not None
        and current_signal_count_bucket not in RESEARCH_CURRENT_SIGNAL_COUNT_BUCKET_KEYS
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported current_signal_count_bucket: {current_signal_count_bucket}",
        )
    if current_signal_pattern_key is not None:
        try:
            current_signal_pattern_key = normalize_research_signal_pattern_key(current_signal_pattern_key)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported current_signal_pattern_key: {current_signal_pattern_key}",
            ) from exc
    if pre_401_signal_pattern_key is not None:
        try:
            pre_401_signal_pattern_key = normalize_research_signal_pattern_key(pre_401_signal_pattern_key)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported pre_401_signal_pattern_key: {pre_401_signal_pattern_key}",
            ) from exc
    if pre_401_gap_bucket is not None and pre_401_gap_bucket not in RESEARCH_PRE_401_GAP_BUCKET_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported pre_401_gap_bucket: {pre_401_gap_bucket}",
        )
    if current_match_level is not None and current_match_level not in RESEARCH_HISTORICAL_MATCH_LEVELS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported current_match_level: {current_match_level}",
        )
    if (
        current_historical_like_bucket is not None
        and current_historical_like_bucket
        not in RESEARCH_HISTORICAL_LIKE_EVENT_COUNT_BUCKET_KEYS
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported current_historical_like_bucket: {current_historical_like_bucket}",
        )
    if (
        current_historical_gap_bucket is not None
        and current_historical_gap_bucket not in RESEARCH_PRE_401_GAP_BUCKET_KEYS
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported current_historical_gap_bucket: {current_historical_gap_bucket}",
        )

    overview = get_research_overview(
        db,
        window_days=window_days,
        provider=provider,
        account_type=account_type,
        current_signal_key=current_signal_key,
        current_status_message=current_status_message,
        current_signal_pattern_key=current_signal_pattern_key,
        current_signal_count_bucket=current_signal_count_bucket,
        pre_401_signal_key=pre_401_signal_key,
        pre_401_status_message=pre_401_status_message,
        pre_401_signal_pattern_key=pre_401_signal_pattern_key,
        pre_401_gap_bucket=pre_401_gap_bucket,
        current_match_level=current_match_level,
        current_signal_min_streak=current_signal_min_streak,
        current_historical_like_bucket=current_historical_like_bucket,
        current_historical_gap_bucket=current_historical_gap_bucket,
        current_historical_event_id=current_historical_event_id,
    )
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
        signal_comparison=[
            ResearchSignalComparisonItem.model_validate(item)
            for item in overview.signal_comparison
        ],
        signal_pattern_comparison=[
            ResearchSignalPatternComparisonItem.model_validate(item)
            for item in overview.signal_pattern_comparison
        ],
        pre_401_insights=ResearchPre401Insights(
            sampled_events=overview.pre_401_insights.sampled_events,
            events_with_previous_snapshot=overview.pre_401_insights.events_with_previous_snapshot,
            previous_to_event_gap_bands=[
                ResearchBucketCount.model_validate(item)
                for item in overview.pre_401_insights.previous_to_event_gap_bands
            ],
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
            signal_pattern_breakdown=[
                ResearchBucketCount.model_validate(item)
                for item in overview.pre_401_insights.signal_pattern_breakdown
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
        current_signal_baseline=ResearchCurrentSignalBaseline(
            observed_accounts=overview.current_signal_baseline.observed_accounts,
            signal_accounts=overview.current_signal_baseline.signal_accounts,
            signal_breakdown=[
                ResearchBucketCount.model_validate(item)
                for item in overview.current_signal_baseline.signal_breakdown
            ],
            signal_pattern_breakdown=[
                ResearchBucketCount.model_validate(item)
                for item in overview.current_signal_baseline.signal_pattern_breakdown
            ],
            signal_count_breakdown=[
                ResearchBucketCount.model_validate(item)
                for item in overview.current_signal_baseline.signal_count_breakdown
            ],
            signal_streak_breakdown=[
                ResearchBucketCount.model_validate(item)
                for item in overview.current_signal_baseline.signal_streak_breakdown
            ],
            historical_match_breakdown=[
                ResearchBucketCount.model_validate(item)
                for item in overview.current_signal_baseline.historical_match_breakdown
            ],
            historical_like_event_count_breakdown=[
                ResearchBucketCount.model_validate(item)
                for item in overview.current_signal_baseline.historical_like_event_count_breakdown
            ],
            historical_match_gap_breakdown=[
                ResearchBucketCount.model_validate(item)
                for item in overview.current_signal_baseline.historical_match_gap_breakdown
            ],
            historical_replay_breakdown=[
                ResearchHistoricalReplayBreakdownItem.model_validate(item)
                for item in overview.current_signal_baseline.historical_replay_breakdown
            ],
            current_signal_group_breakdown=[
                ResearchCurrentSignalGroupBreakdownItem.model_validate(item)
                for item in overview.current_signal_baseline.current_signal_group_breakdown
            ],
            top_status_messages=[
                ResearchBucketCount.model_validate(item)
                for item in overview.current_signal_baseline.top_status_messages
            ],
            recent_samples=[
                ResearchCurrentSignalSample.model_validate(item)
                for item in overview.current_signal_baseline.recent_samples
            ],
        ),
    )
