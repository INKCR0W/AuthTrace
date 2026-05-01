export type JsonObject = Record<string, unknown>;

export interface LatestScanJobSummary {
  id: number;
  trigger_mode: string;
  status: string;
  scan_started_at: string;
  scan_finished_at: string | null;
  total_accounts: number;
  eligible_accounts: number;
  scanned_accounts: number;
  success_accounts: number;
  failed_accounts: number;
  new_401_events: number;
  new_quota_events: number;
  duration_ms: number | null;
  error_message: string | null;
}

export interface OverviewTrendPoint {
  bucket_start: string;
  became_401_count: number;
}

export interface DimensionBreakdownItem {
  value: string | null;
  label: string;
  total_accounts: number;
  active_accounts: number;
  disabled_accounts: number;
  current_401_accounts: number;
  current_invalid_quota_accounts: number;
  became_401_events_last_24h: number;
  current_401_rate: number;
  current_invalid_quota_rate: number;
}

export interface DashboardOverviewResponse {
  total_accounts: number;
  active_accounts: number;
  disabled_accounts: number;
  deleted_accounts: number;
  current_401_accounts: number;
  current_invalid_quota_accounts: number;
  new_401_events_last_24h: number;
  new_quota_events_last_24h: number;
  recent_401_trend: OverviewTrendPoint[];
  provider_breakdown: DimensionBreakdownItem[];
  account_type_breakdown: DimensionBreakdownItem[];
  latest_scan_job: LatestScanJobSummary | null;
}

export interface ResearchOverviewSummary {
  active_accounts: number;
  current_401_accounts: number;
  current_401_rate: number;
  became_401_events: number;
  affected_accounts: number;
  affected_provider_groups: number;
  sampled_previous_snapshots: number;
}

export interface ResearchCombinationBreakdownItem {
  label: string;
  provider: string | null;
  account_type: string | null;
  total_accounts: number;
  current_401_accounts: number;
  current_401_rate: number;
  became_401_events: number;
  affected_accounts: number;
  last_became_401_at: string | null;
}

export interface ResearchHourlyDistributionPoint {
  hour_of_day: number;
  label: string;
  became_401_count: number;
}

export interface ResearchBucketCount {
  key: string;
  label: string;
  count: number;
}

export interface ResearchPre401Insights {
  sampled_events: number;
  events_with_previous_snapshot: number;
  weekly_used_percent_bands: ResearchBucketCount[];
  short_used_percent_bands: ResearchBucketCount[];
  signal_breakdown: ResearchBucketCount[];
  top_status_messages: ResearchBucketCount[];
}

export interface ResearchCurrentSignalSample {
  account_id: number;
  account_name: string;
  provider: string | null;
  account_type: string | null;
  current_last_checked_at: string | null;
  current_weekly_used_percent: string | null;
  current_short_used_percent: string | null;
  current_remaining: string | null;
  current_limit_reached: boolean | null;
  current_allowed: boolean | null;
  status_message_excerpt: string | null;
  signal_labels: string[];
}

export interface ResearchCurrentSignalBaseline {
  observed_accounts: number;
  signal_accounts: number;
  signal_breakdown: ResearchBucketCount[];
  signal_pattern_breakdown: ResearchBucketCount[];
  top_status_messages: ResearchBucketCount[];
  recent_samples: ResearchCurrentSignalSample[];
}

export interface ResearchOverviewResponse {
  window_days: number;
  summary: ResearchOverviewSummary;
  provider_account_type_breakdown: ResearchCombinationBreakdownItem[];
  event_hour_distribution: ResearchHourlyDistributionPoint[];
  pre_401_insights: ResearchPre401Insights;
  recent_event_samples: ResearchEventSample[];
  current_signal_baseline: ResearchCurrentSignalBaseline;
}

export interface ResearchEventSample {
  event_id: number;
  account_id: number;
  account_name: string;
  provider: string | null;
  account_type: string | null;
  event_time: string;
  current_is_401: boolean;
  previous_snapshot_id: number | null;
  previous_checked_at: string | null;
  previous_weekly_used_percent: string | null;
  previous_short_used_percent: string | null;
  previous_remaining: string | null;
  previous_limit_reached: boolean | null;
  previous_allowed: boolean | null;
  previous_status_message: string | null;
}

export interface DefaultManagementSourceResponse {
  source_id: number | null;
  source_key: string;
  source_name: string;
  base_url: string | null;
  configured: boolean;
  is_enabled: boolean;
  target_type: string | null;
  provider: string | null;
  scheduler_enabled: boolean;
  scheduler_running: boolean;
  scheduler_interval_minutes: number;
  scheduler_next_run_at: string | null;
  scheduler_last_started_at: string | null;
  scheduler_last_finished_at: string | null;
  scheduler_last_status: string | null;
  scheduler_last_error_message: string | null;
}

export interface AuthFileSyncResponse {
  scan_job_id: number;
  source_id: number;
  source_key: string;
  status: string;
  total_accounts: number;
  synced_accounts: number;
  eligible_accounts: number;
  skipped_accounts: number;
  missing_auth_index_accounts: number;
  scanned_accounts: number;
  successful_snapshots: number;
  failed_snapshots: number;
}

export interface AuthFileSyncConflictDetail {
  message: string;
  running_scan_job_id: number;
  source_id: number;
  scan_started_at: string | null;
}

export interface ScanJobListResponse {
  total: number;
  limit: number;
  offset: number;
  items: LatestScanJobSummary[];
}

export interface ScanJobSnapshotStats {
  total_snapshots: number;
  success_snapshots: number;
  partial_failed_snapshots: number;
  failed_snapshots: number;
  is_401_snapshots: number;
  invalid_quota_snapshots: number;
}

export interface ScanJobDiagnosticBucket {
  key: string;
  label: string;
  count: number;
}

export interface ScanJobDiagnosticSummary {
  abnormal_probe_status_samples: number;
  abnormal_probe_status_breakdown: ScanJobDiagnosticBucket[];
  top_failure_reasons: ScanJobDiagnosticBucket[];
}

export interface ScanJobAccountRef {
  id: number;
  name: string;
  auth_index: string;
  provider: string | null;
  account_type: string | null;
  disabled: boolean;
}

export interface ScanJobSnapshotSample {
  id: number;
  account_id: number;
  scan_job_id: number;
  checked_at: string;
  snapshot_status: string;
  probe_status_code: number | null;
  is_401: boolean;
  quota_status_code: number | null;
  invalid_quota: boolean;
  quota_source: string | null;
  weekly_used_percent: string | null;
  weekly_reset_at: string | null;
  short_used_percent: string | null;
  short_reset_at: string | null;
  remaining: string | null;
  limit_reached: boolean | null;
  allowed: boolean | null;
  status_message: string | null;
  raw_auth_file_json: JsonObject | null;
  raw_usage_json: JsonObject | null;
  error_message: string | null;
  created_at: string;
  account: ScanJobAccountRef;
}

export interface ScanJobDetailResponse {
  item: LatestScanJobSummary;
  snapshot_stats: ScanJobSnapshotStats;
  diagnostic_summary: ScanJobDiagnosticSummary;
  recent_failure_samples: ScanJobSnapshotSample[];
  recent_401_samples: ScanJobSnapshotSample[];
  recent_quota_samples: ScanJobSnapshotSample[];
}

export interface AccountSummary {
  id: number;
  source_id: number;
  auth_index: string;
  name: string;
  account: string | null;
  email: string | null;
  account_type: string | null;
  provider: string | null;
  chatgpt_account_id: string | null;
  disabled: boolean;
  upstream_status: string | null;
  status_message: string | null;
  current_status_code: number | null;
  current_is_401: boolean;
  current_invalid_quota: boolean;
  current_weekly_used_percent: string | null;
  current_weekly_reset_at: string | null;
  current_short_used_percent: string | null;
  current_short_reset_at: string | null;
  current_remaining: string | null;
  current_limit_reached: boolean | null;
  current_allowed: boolean | null;
  current_last_checked_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  source_deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccountSnapshotSummary {
  id: number;
  account_id: number;
  scan_job_id: number;
  checked_at: string;
  snapshot_status: string;
  probe_status_code: number | null;
  is_401: boolean;
  quota_status_code: number | null;
  invalid_quota: boolean;
  quota_source: string | null;
  weekly_used_percent: string | null;
  weekly_reset_at: string | null;
  short_used_percent: string | null;
  short_reset_at: string | null;
  remaining: string | null;
  limit_reached: boolean | null;
  allowed: boolean | null;
  status_message: string | null;
  raw_auth_file_json: JsonObject | null;
  raw_usage_json: JsonObject | null;
  error_message: string | null;
  created_at: string;
}

export interface AccountEventSummary {
  id: number;
  account_id: number;
  event_type: string;
  event_time: string;
  related_snapshot_id: number;
  previous_snapshot_id: number | null;
  from_status_code: number | null;
  to_status_code: number | null;
  from_is_401: boolean | null;
  to_is_401: boolean | null;
  from_invalid_quota: boolean | null;
  to_invalid_quota: boolean | null;
  from_disabled: boolean | null;
  to_disabled: boolean | null;
  note: string | null;
  created_at: string;
}

export interface AccountCohortBreakdown {
  label: string;
  provider: string | null;
  account_type: string | null;
  total_accounts: number;
  active_accounts: number;
  disabled_accounts: number;
  current_401_accounts: number;
  current_invalid_quota_accounts: number;
  became_401_events_last_24h: number;
  quota_exhausted_events_last_24h: number;
  checked_accounts_last_24h: number;
  high_weekly_accounts: number;
  high_short_accounts: number;
  current_limit_reached_accounts: number;
  current_blocked_accounts: number;
  current_401_rate: number;
  current_invalid_quota_rate: number;
}

export interface AccountCohortUsagePosition {
  weekly_compared_accounts: number;
  weekly_used_percent: string | null;
  weekly_rank_desc: number | null;
  short_compared_accounts: number;
  short_used_percent: string | null;
  short_rank_desc: number | null;
}

export interface AccountRiskSignal {
  key: string;
  label: string;
  tone: "success" | "warning" | "danger" | "muted";
  detail: string;
}

export interface AccountRiskOverview {
  level: "low" | "medium" | "high" | "critical";
  headline: string;
  summary: string;
  signal_count: number;
  signals: AccountRiskSignal[];
}

export interface AccountCohortTrendPoint {
  bucket_start: string;
  snapshot_count: number;
  is_401_count: number;
  invalid_quota_count: number;
  failed_count: number;
  high_weekly_count: number;
  high_short_count: number;
}

export interface AccountListResponse {
  total: number;
  limit: number;
  offset: number;
  items: AccountSummary[];
}

export interface AccountDetailResponse {
  account: AccountSummary;
  recent_snapshots: AccountSnapshotSummary[];
  recent_events: AccountEventSummary[];
  provider_cohort: AccountCohortBreakdown;
  account_type_cohort: AccountCohortBreakdown;
  provider_account_type_cohort: AccountCohortBreakdown;
  cohort_usage_position: AccountCohortUsagePosition;
  risk_overview: AccountRiskOverview;
  provider_account_type_trend: AccountCohortTrendPoint[];
}

export interface EventListItem {
  event: AccountEventSummary;
  account: AccountSummary;
  related_snapshot: AccountSnapshotSummary;
  previous_snapshot: AccountSnapshotSummary | null;
}

export interface EventListResponse {
  total: number;
  limit: number;
  offset: number;
  items: EventListItem[];
}

export interface EventDetailResponse {
  item: EventListItem;
  context_snapshots: AccountSnapshotSummary[];
  context_events: AccountEventSummary[];
}
