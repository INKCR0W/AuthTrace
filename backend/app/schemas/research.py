from __future__ import annotations

from datetime import datetime
from decimal import Decimal

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


class ResearchSignalComparisonItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    pre_401_count: int
    pre_401_rate: float
    current_count: int
    current_rate: float
    rate_gap: float


class ResearchSignalPatternComparisonItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    pre_401_count: int
    pre_401_rate: float
    current_count: int
    current_rate: float
    rate_gap: float


class ResearchPre401Insights(BaseModel):
    sampled_events: int
    events_with_previous_snapshot: int
    previous_to_event_gap_bands: list[ResearchBucketCount] = Field(default_factory=list)
    weekly_used_percent_bands: list[ResearchBucketCount] = Field(default_factory=list)
    short_used_percent_bands: list[ResearchBucketCount] = Field(default_factory=list)
    signal_breakdown: list[ResearchBucketCount] = Field(default_factory=list)
    signal_pattern_breakdown: list[ResearchBucketCount] = Field(default_factory=list)
    top_status_messages: list[ResearchBucketCount] = Field(default_factory=list)


class ResearchEventSample(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: int
    account_id: int
    account_name: str
    provider: str | None = None
    account_type: str | None = None
    event_time: datetime
    current_is_401: bool
    previous_snapshot_id: int | None = None
    previous_checked_at: datetime | None = None
    previous_to_event_gap_minutes: int | None = None
    previous_weekly_used_percent: Decimal | None = None
    previous_short_used_percent: Decimal | None = None
    previous_remaining: Decimal | None = None
    previous_limit_reached: bool | None = None
    previous_allowed: bool | None = None
    previous_status_message: str | None = None


class ResearchCurrentSignalSample(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: int
    account_name: str
    provider: str | None = None
    account_type: str | None = None
    current_last_checked_at: datetime | None = None
    current_weekly_used_percent: Decimal | None = None
    current_short_used_percent: Decimal | None = None
    current_remaining: Decimal | None = None
    current_limit_reached: bool | None = None
    current_allowed: bool | None = None
    status_message_excerpt: str | None = None
    signal_labels: list[str] = Field(default_factory=list)
    consecutive_signal_snapshots: int
    signal_started_at: datetime | None = None


class ResearchCurrentSignalGroupBreakdownItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    provider: str | None = None
    account_type: str | None = None
    observed_accounts: int
    signal_accounts: int
    signal_rate: float
    multi_round_signal_accounts: int
    top_signal_pattern: str | None = None


class ResearchCurrentSignalBaseline(BaseModel):
    observed_accounts: int
    signal_accounts: int
    signal_breakdown: list[ResearchBucketCount] = Field(default_factory=list)
    signal_pattern_breakdown: list[ResearchBucketCount] = Field(default_factory=list)
    signal_streak_breakdown: list[ResearchBucketCount] = Field(default_factory=list)
    current_signal_group_breakdown: list[ResearchCurrentSignalGroupBreakdownItem] = Field(default_factory=list)
    top_status_messages: list[ResearchBucketCount] = Field(default_factory=list)
    recent_samples: list[ResearchCurrentSignalSample] = Field(default_factory=list)


class ResearchOverviewResponse(BaseModel):
    window_days: int
    summary: ResearchOverviewSummary
    provider_account_type_breakdown: list[ResearchCombinationBreakdownItem] = Field(default_factory=list)
    event_hour_distribution: list[ResearchHourlyDistributionPoint] = Field(default_factory=list)
    signal_comparison: list[ResearchSignalComparisonItem] = Field(default_factory=list)
    signal_pattern_comparison: list[ResearchSignalPatternComparisonItem] = Field(default_factory=list)
    pre_401_insights: ResearchPre401Insights
    recent_event_samples: list[ResearchEventSample] = Field(default_factory=list)
    current_signal_baseline: ResearchCurrentSignalBaseline
