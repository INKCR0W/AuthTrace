from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResearchOverviewSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    active_accounts: int
    current_401_accounts: int
    current_401_rate: float
    became_401_events: int
    affected_accounts: int
    affected_provider_groups: int
    sampled_previous_snapshots: int


class ResearchCombinationBreakdownItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    provider: str | None = None
    account_type: str | None = None
    total_accounts: int
    current_401_accounts: int
    current_401_rate: float
    became_401_events: int
    affected_accounts: int
    last_became_401_at: datetime | None = None


class ResearchHourlyDistributionPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hour_of_day: int
    label: str
    became_401_count: int


class ResearchBucketCount(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    count: int


class ResearchPre401Insights(BaseModel):
    sampled_events: int
    events_with_previous_snapshot: int
    weekly_used_percent_bands: list[ResearchBucketCount] = Field(default_factory=list)
    short_used_percent_bands: list[ResearchBucketCount] = Field(default_factory=list)
    signal_breakdown: list[ResearchBucketCount] = Field(default_factory=list)
    top_status_messages: list[ResearchBucketCount] = Field(default_factory=list)


class ResearchOverviewResponse(BaseModel):
    window_days: int
    summary: ResearchOverviewSummary
    provider_account_type_breakdown: list[ResearchCombinationBreakdownItem] = Field(default_factory=list)
    event_hour_distribution: list[ResearchHourlyDistributionPoint] = Field(default_factory=list)
    pre_401_insights: ResearchPre401Insights
