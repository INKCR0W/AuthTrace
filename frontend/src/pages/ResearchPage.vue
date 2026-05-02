<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import type { LocationQuery, LocationQueryRaw, LocationQueryValue } from "vue-router";

import { getResearchOverview } from "@/api/client";
import DistributionBarChart from "@/components/DistributionBarChart.vue";
import MetricCard from "@/components/MetricCard.vue";
import StatusPill from "@/components/StatusPill.vue";
import { formatCount, formatDateTime, formatMinutesSpan, formatPercent, formatRemaining } from "@/lib/format";
import type {
  ResearchBucketCount,
  ResearchCurrentSignalSample,
  ResearchCurrentSignalGroupSample,
  ResearchEventSample,
  ResearchOverviewResponse,
} from "@/types/api";

const CURRENT_SIGNAL_OPTIONS = [
  { key: "weekly_ge_90", label: "周额度 >= 90%" },
  { key: "short_ge_90", label: "短周期 >= 90%" },
  { key: "limit_reached", label: "limit_reached=true" },
  { key: "allowed_false", label: "allowed=false" },
  { key: "remaining_empty", label: "remaining <= 0" },
  { key: "status_message_present", label: "存在 status_message" },
] as const;
const CURRENT_MATCH_OPTIONS = [
  { key: "exact_pattern", label: "仅看完全同模式" },
  { key: "covered_pattern", label: "仅看被历史覆盖" },
  { key: "partial_overlap", label: "仅看部分重合" },
  { key: "no_overlap", label: "仅看未重合" },
  { key: "no_history", label: "仅看暂无历史样本" },
] as const;
const CURRENT_STREAK_OPTIONS = [
  { value: "2", label: "连续至少 2 轮" },
  { value: "3", label: "连续至少 3 轮" },
  { value: "4", label: "连续至少 4 轮" },
] as const;
const PRE_401_GAP_OPTIONS = [
  { key: "lt_15m", label: "15 分钟内" },
  { key: "15m_1h", label: "15-60 分钟" },
  { key: "1h_6h", label: "1-6 小时" },
  { key: "6h_24h", label: "6-24 小时" },
  { key: "24h_plus", label: "24 小时以上" },
] as const;
const WINDOW_DAY_OPTIONS = [7, 14, 30] as const;
const currentSignalLabelMap = Object.fromEntries(
  CURRENT_SIGNAL_OPTIONS.map((item) => [item.key, item.label]),
) as Record<string, string>;
const currentMatchLabelMap = Object.fromEntries(
  CURRENT_MATCH_OPTIONS.map((item) => [item.key, item.label]),
) as Record<string, string>;
const pre401GapLabelMap = Object.fromEntries(
  PRE_401_GAP_OPTIONS.map((item) => [item.key, item.label]),
) as Record<string, string>;
const allowedCurrentSignalKeys = new Set(CURRENT_SIGNAL_OPTIONS.map((item) => item.key));
const allowedCurrentMatchKeys = new Set(CURRENT_MATCH_OPTIONS.map((item) => item.key));
const allowedCurrentSignalMinStreaks = new Set(CURRENT_STREAK_OPTIONS.map((item) => item.value));
const allowedPre401GapKeys = new Set(PRE_401_GAP_OPTIONS.map((item) => item.key));
const currentSignalOrderMap = new Map(CURRENT_SIGNAL_OPTIONS.map((item, index) => [item.key, index]));

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const error = ref("");
const windowDays = ref(7);
const overview = ref<ResearchOverviewResponse | null>(null);
const hasInitializedRouteState = ref(false);
const filters = reactive({
  provider: "",
  accountType: "",
  currentSignalKey: "",
  currentSignalPatternKey: "",
  pre401SignalKey: "",
  pre401SignalPatternKey: "",
  pre401GapBucket: "",
  currentMatchLevel: "",
  currentSignalMinStreak: "",
  currentHistoricalGapBucket: "",
});

interface ResearchRouteState {
  windowDays: number;
  provider: string;
  accountType: string;
  currentSignalKey: string;
  currentSignalPatternKey: string;
  pre401SignalKey: string;
  pre401SignalPatternKey: string;
  pre401GapBucket: string;
  currentMatchLevel: string;
  currentSignalMinStreak: string;
  currentHistoricalGapBucket: string;
}

const researchRouteQueryKeys = [
  "window_days",
  "provider",
  "account_type",
  "current_signal_key",
  "current_signal_pattern_key",
  "pre_401_signal_key",
  "pre_401_signal_pattern_key",
  "pre_401_gap_bucket",
  "current_match_level",
  "current_signal_min_streak",
  "current_historical_gap_bucket",
] as const;

const hourlyLabels = computed(() => overview.value?.event_hour_distribution.map((item) => item.label) ?? []);
const hourlyValues = computed(() => overview.value?.event_hour_distribution.map((item) => item.became_401_count) ?? []);
const weeklyBandLabels = computed(
  () => overview.value?.pre_401_insights.weekly_used_percent_bands.map((item) => item.label) ?? [],
);
const weeklyBandValues = computed(
  () => overview.value?.pre_401_insights.weekly_used_percent_bands.map((item) => item.count) ?? [],
);
const shortBandLabels = computed(
  () => overview.value?.pre_401_insights.short_used_percent_bands.map((item) => item.label) ?? [],
);
const shortBandValues = computed(
  () => overview.value?.pre_401_insights.short_used_percent_bands.map((item) => item.count) ?? [],
);
const gapBandLabels = computed(
  () => overview.value?.pre_401_insights.previous_to_event_gap_bands.map((item) => item.label) ?? [],
);
const gapBandValues = computed(
  () => overview.value?.pre_401_insights.previous_to_event_gap_bands.map((item) => item.count) ?? [],
);
const normalizedProvider = computed(() => filters.provider.trim());
const normalizedAccountType = computed(() => filters.accountType.trim());
const normalizedCurrentSignalKey = computed(() => filters.currentSignalKey.trim());
const normalizedCurrentSignalPatternKey = computed(() => filters.currentSignalPatternKey.trim());
const normalizedPre401SignalKey = computed(() => filters.pre401SignalKey.trim());
const normalizedPre401SignalPatternKey = computed(() => filters.pre401SignalPatternKey.trim());
const normalizedPre401GapBucket = computed(() => filters.pre401GapBucket.trim());
const normalizedCurrentMatchLevel = computed(() => filters.currentMatchLevel.trim());
const normalizedCurrentSignalMinStreak = computed(() => filters.currentSignalMinStreak.trim());
const normalizedCurrentHistoricalGapBucket = computed(() => filters.currentHistoricalGapBucket.trim());
const selectedCurrentSignalLabel = computed(() => {
  if (!normalizedCurrentSignalKey.value) {
    return "";
  }
  return currentSignalLabelMap[normalizedCurrentSignalKey.value] ?? normalizedCurrentSignalKey.value;
});
const selectedPre401SignalLabel = computed(() => {
  if (!normalizedPre401SignalKey.value) {
    return "";
  }
  return currentSignalLabelMap[normalizedPre401SignalKey.value] ?? normalizedPre401SignalKey.value;
});
function formatPatternLabel(patternKey: string) {
  return patternKey
    .split("|")
    .filter(Boolean)
    .map((part) => currentSignalLabelMap[part] ?? part)
    .join(" / ");
}

function buildPatternOptions(items: ResearchBucketCount[], selectedKey: string) {
  if (!selectedKey) {
    return items;
  }
  if (items.some((item) => item.key === selectedKey)) {
    return items;
  }
  return [
    {
      key: selectedKey,
      label: formatPatternLabel(selectedKey),
      count: 0,
    },
    ...items,
  ];
}

const currentSignalPatternOptions = computed(() =>
  buildPatternOptions(
    overview.value?.current_signal_baseline.signal_pattern_breakdown ?? [],
    normalizedCurrentSignalPatternKey.value,
  ),
);
const pre401SignalPatternOptions = computed(() =>
  buildPatternOptions(
    overview.value?.pre_401_insights.signal_pattern_breakdown ?? [],
    normalizedPre401SignalPatternKey.value,
  ),
);
const selectedCurrentSignalPatternLabel = computed(() => {
  if (!normalizedCurrentSignalPatternKey.value) {
    return "";
  }
  const matched = currentSignalPatternOptions.value.find(
    (item) => item.key === normalizedCurrentSignalPatternKey.value,
  );
  return matched?.label ?? formatPatternLabel(normalizedCurrentSignalPatternKey.value);
});
const selectedPre401SignalPatternLabel = computed(() => {
  if (!normalizedPre401SignalPatternKey.value) {
    return "";
  }
  const matched = pre401SignalPatternOptions.value.find(
    (item) => item.key === normalizedPre401SignalPatternKey.value,
  );
  return matched?.label ?? formatPatternLabel(normalizedPre401SignalPatternKey.value);
});
const selectedPre401GapBucketLabel = computed(() => {
  if (!normalizedPre401GapBucket.value) {
    return "";
  }
  return pre401GapLabelMap[normalizedPre401GapBucket.value] ?? normalizedPre401GapBucket.value;
});
const selectedCurrentMatchLabel = computed(() => {
  if (!normalizedCurrentMatchLevel.value) {
    return "";
  }
  return currentMatchLabelMap[normalizedCurrentMatchLevel.value] ?? normalizedCurrentMatchLevel.value;
});
const selectedCurrentSignalMinStreakLabel = computed(() => {
  if (!normalizedCurrentSignalMinStreak.value) {
    return "";
  }
  return `连续至少 ${normalizedCurrentSignalMinStreak.value} 轮`;
});
const selectedCurrentHistoricalGapBucketLabel = computed(() => {
  if (!normalizedCurrentHistoricalGapBucket.value) {
    return "";
  }
  return pre401GapLabelMap[normalizedCurrentHistoricalGapBucket.value] ?? normalizedCurrentHistoricalGapBucket.value;
});
const hasScopedFilters = computed(
  () =>
    Boolean(
      normalizedProvider.value ||
        normalizedAccountType.value ||
        normalizedCurrentSignalKey.value ||
        normalizedCurrentSignalPatternKey.value ||
        normalizedPre401SignalKey.value ||
        normalizedPre401SignalPatternKey.value ||
        normalizedPre401GapBucket.value ||
        normalizedCurrentMatchLevel.value ||
        normalizedCurrentSignalMinStreak.value ||
        normalizedCurrentHistoricalGapBucket.value,
    ),
);
const scopeSummary = computed(() => {
  const segments: string[] = [];

  if (normalizedProvider.value) {
    segments.push(`provider=${normalizedProvider.value}`);
  }
  if (normalizedAccountType.value) {
    segments.push(`类型=${normalizedAccountType.value}`);
  }
  if (selectedCurrentSignalLabel.value) {
    segments.push(`当前信号=${selectedCurrentSignalLabel.value}`);
  }
  if (selectedCurrentSignalPatternLabel.value) {
    segments.push(`当前模式=${selectedCurrentSignalPatternLabel.value}`);
  }
  if (selectedPre401SignalLabel.value) {
    segments.push(`前序信号=${selectedPre401SignalLabel.value}`);
  }
  if (selectedPre401SignalPatternLabel.value) {
    segments.push(`前序模式=${selectedPre401SignalPatternLabel.value}`);
  }
  if (selectedPre401GapBucketLabel.value) {
    segments.push(`前序新鲜度=${selectedPre401GapBucketLabel.value}`);
  }
  if (selectedCurrentMatchLabel.value) {
    segments.push(`历史贴近=${selectedCurrentMatchLabel.value}`);
  }
  if (selectedCurrentSignalMinStreakLabel.value) {
    segments.push(selectedCurrentSignalMinStreakLabel.value);
  }
  if (selectedCurrentHistoricalGapBucketLabel.value) {
    segments.push(`最佳历史证据=${selectedCurrentHistoricalGapBucketLabel.value}`);
  }

  return segments.length ? segments.join(" / ") : "全部账号";
});
const currentSignalScopeHint = computed(() => {
  if (!selectedCurrentSignalLabel.value) {
    if (
      !selectedCurrentSignalPatternLabel.value &&
      !selectedCurrentMatchLabel.value &&
      !selectedCurrentSignalMinStreakLabel.value &&
      !selectedCurrentHistoricalGapBucketLabel.value
    ) {
      return "";
    }
  }
  const segments: string[] = [];
  if (selectedCurrentSignalLabel.value) {
    segments.push(`当前信号“${selectedCurrentSignalLabel.value}”`);
  }
  if (selectedCurrentSignalPatternLabel.value) {
    segments.push(`当前模式“${selectedCurrentSignalPatternLabel.value}”`);
  }
  if (selectedCurrentMatchLabel.value) {
    segments.push(`历史贴近度“${selectedCurrentMatchLabel.value}”`);
  }
  if (selectedCurrentSignalMinStreakLabel.value) {
    segments.push(selectedCurrentSignalMinStreakLabel.value);
  }
  if (selectedCurrentHistoricalGapBucketLabel.value) {
    segments.push(`最佳历史证据“${selectedCurrentHistoricalGapBucketLabel.value}”`);
  }
  return `当前基线已按${segments.join(" + ")}收窄；下方仍会继续展示这些样本共现的其他信号，便于判断伴随模式。`;
});
const dominantCurrentSignalPattern = computed(
  () => overview.value?.current_signal_baseline.signal_pattern_breakdown[0] ?? null,
);
const dominantPre401SignalPattern = computed(
  () => overview.value?.pre_401_insights.signal_pattern_breakdown[0] ?? null,
);
const leadingSignalComparison = computed(() => {
  const item = overview.value?.signal_comparison[0] ?? null;
  if (!item || item.rate_gap <= 0) {
    return null;
  }
  return item;
});
const leadingSignalPatternComparison = computed(() => {
  const item = overview.value?.signal_pattern_comparison[0] ?? null;
  if (!item || item.rate_gap <= 0) {
    return null;
  }
  return item;
});
const leadingHistoricalLikeGroup = computed(() => {
  const item = overview.value?.current_signal_baseline.current_signal_group_breakdown[0] ?? null;
  if (!item || item.historical_like_accounts <= 0) {
    return null;
  }
  return item;
});
const hasHistoricalPreviousSamples = computed(
  () => (overview.value?.summary.sampled_previous_snapshots ?? 0) > 0,
);
const dominantCurrentSignalPatternSummary = computed(() => {
  const baseline = overview.value?.current_signal_baseline;
  const dominantPattern = dominantCurrentSignalPattern.value;

  if (!baseline || !dominantPattern || baseline.signal_accounts === 0) {
    return "";
  }

  return `当前最常见的信号组合覆盖 ${formatCount(dominantPattern.count)} / ${formatCount(baseline.signal_accounts)} 个样本：${dominantPattern.label}`;
});
const leadingHistoricalMatchSummary = computed(() => {
  const baseline = overview.value?.current_signal_baseline;
  const item = baseline?.historical_match_breakdown[0] ?? null;

  if (!baseline || !item || baseline.signal_accounts === 0) {
    return "";
  }

  return `${item.label}的当前样本有 ${formatCount(item.count)} / ${formatCount(baseline.signal_accounts)} 个，可优先回放这些仍为非 401 的账号。`;
});
const dominantPre401SignalPatternSummary = computed(() => {
  const insights = overview.value?.pre_401_insights;
  const dominantPattern = dominantPre401SignalPattern.value;

  if (!insights || !dominantPattern || insights.events_with_previous_snapshot === 0) {
    return "";
  }

  return `历史 401 前最常见的信号组合覆盖 ${formatCount(dominantPattern.count)} / ${formatCount(insights.events_with_previous_snapshot)} 个可回放样本：${dominantPattern.label}`;
});
const leadingSignalComparisonSummary = computed(() => {
  const item = leadingSignalComparison.value;
  if (!item) {
    return "";
  }

  return `${item.label} 在历史 401 前的命中率比当前基线高 ${formatPercent(item.rate_gap)}，可优先作为前序研究信号关注。`;
});
const leadingSignalPatternComparisonSummary = computed(() => {
  const item = leadingSignalPatternComparison.value;
  if (!item) {
    return "";
  }

  return `组合模式“${item.label}”在历史 401 前的命中率比当前基线高 ${formatPercent(item.rate_gap)}，更适合作为优先回放的前序样本画像。`;
});
const leadingHistoricalLikeGroupSummary = computed(() => {
  const item = leadingHistoricalLikeGroup.value;
  if (!item) {
    return "";
  }

  const segments = [
    `${item.label} 当前有 ${formatCount(item.historical_like_accounts)} 个样本与历史 401 前模式高度贴近，占该组研究信号账号的 ${formatPercent(item.historical_like_rate)}`,
  ];
  if (item.top_historical_gap_label && item.top_historical_gap_count > 0) {
    segments.push(`其中最常命中的历史证据新鲜度是 ${item.top_historical_gap_label}（${formatCount(item.top_historical_gap_count)} 个样本）`);
  }
  return `${segments.join("，")}。`;
});

function syncFilters(next: Partial<typeof filters>) {
  if (next.provider !== undefined) {
    filters.provider = next.provider;
  }
  if (next.accountType !== undefined) {
    filters.accountType = next.accountType;
  }
  if (next.currentSignalKey !== undefined) {
    filters.currentSignalKey = next.currentSignalKey;
  }
  if (next.currentSignalPatternKey !== undefined) {
    filters.currentSignalPatternKey = next.currentSignalPatternKey;
  }
  if (next.pre401SignalKey !== undefined) {
    filters.pre401SignalKey = next.pre401SignalKey;
  }
  if (next.pre401SignalPatternKey !== undefined) {
    filters.pre401SignalPatternKey = next.pre401SignalPatternKey;
  }
  if (next.pre401GapBucket !== undefined) {
    filters.pre401GapBucket = next.pre401GapBucket;
  }
  if (next.currentMatchLevel !== undefined) {
    filters.currentMatchLevel = next.currentMatchLevel;
  }
  if (next.currentSignalMinStreak !== undefined) {
    filters.currentSignalMinStreak = next.currentSignalMinStreak;
  }
  if (next.currentHistoricalGapBucket !== undefined) {
    filters.currentHistoricalGapBucket = next.currentHistoricalGapBucket;
  }
}

function applyCurrentSignalFilter(signalKey: string) {
  syncFilters({
    currentSignalKey: signalKey,
    currentSignalPatternKey: "",
  });
  void loadOverview();
}

function applyCurrentSignalPatternFilter(patternKey: string) {
  syncFilters({
    currentSignalKey: "",
    currentSignalPatternKey: patternKey,
  });
  void loadOverview();
}

function applyPre401SignalFilter(signalKey: string) {
  syncFilters({
    pre401SignalKey: signalKey,
    pre401SignalPatternKey: "",
  });
  void loadOverview();
}

function applyPre401SignalPatternFilter(patternKey: string) {
  syncFilters({
    pre401SignalKey: "",
    pre401SignalPatternKey: patternKey,
  });
  void loadOverview();
}

function applyPre401GapBucketFilter(gapBucket: string) {
  syncFilters({
    pre401GapBucket: gapBucket,
  });
  void loadOverview();
}

function applyCurrentMatchLevelFilter(matchLevel: string) {
  syncFilters({
    currentMatchLevel: matchLevel,
  });
  void loadOverview();
}

function applyCurrentHistoricalGapBucketFilter(gapBucket: string) {
  syncFilters({
    currentHistoricalGapBucket: gapBucket,
  });
  void loadOverview();
}

function applyScopeFilter(provider: string | null, accountType: string | null) {
  syncFilters({
    provider: provider ?? "",
    accountType: accountType ?? "",
  });
  void loadOverview();
}

function isCurrentSignalFilterActive(signalKey: string) {
  return normalizedCurrentSignalKey.value === signalKey;
}

function isCurrentSignalPatternFilterActive(patternKey: string) {
  return normalizedCurrentSignalPatternKey.value === patternKey;
}

function isPre401SignalFilterActive(signalKey: string) {
  return normalizedPre401SignalKey.value === signalKey;
}

function isPre401SignalPatternFilterActive(patternKey: string) {
  return normalizedPre401SignalPatternKey.value === patternKey;
}

function isPre401GapBucketFilterActive(gapBucket: string) {
  return normalizedPre401GapBucket.value === gapBucket;
}

function isCurrentMatchLevelFilterActive(matchLevel: string) {
  return normalizedCurrentMatchLevel.value === matchLevel;
}

function isCurrentHistoricalGapBucketFilterActive(gapBucket: string) {
  return normalizedCurrentHistoricalGapBucket.value === gapBucket;
}

function isScopeFilterActive(provider: string | null, accountType: string | null) {
  return normalizedProvider.value === (provider ?? "") && normalizedAccountType.value === (accountType ?? "");
}

function normalizeQueryValue(value: LocationQueryValue | LocationQueryValue[] | undefined) {
  if (Array.isArray(value)) {
    return typeof value[0] === "string" ? value[0].trim() : "";
  }
  return typeof value === "string" ? value.trim() : "";
}

function normalizeAllowedValue(value: string, allowedValues: Set<string>) {
  return allowedValues.has(value) ? value : "";
}

function normalizePatternKeyValue(value: string) {
  if (!value) {
    return "";
  }

  const segments = value
    .split("|")
    .map((segment) => segment.trim())
    .filter(Boolean);

  if (!segments.length) {
    return "";
  }

  const uniqueSegments = new Set<string>();
  for (const segment of segments) {
    if (!allowedCurrentSignalKeys.has(segment) || uniqueSegments.has(segment)) {
      return "";
    }
    uniqueSegments.add(segment);
  }

  return [...uniqueSegments]
    .sort((left, right) => (currentSignalOrderMap.get(left) ?? 0) - (currentSignalOrderMap.get(right) ?? 0))
    .join("|");
}

function normalizeWindowDayValue(value: string) {
  const parsed = Number(value);
  return WINDOW_DAY_OPTIONS.includes(parsed as (typeof WINDOW_DAY_OPTIONS)[number]) ? parsed : 7;
}

function buildRouteStateFromQuery(query: LocationQuery): ResearchRouteState {
  return {
    windowDays: normalizeWindowDayValue(normalizeQueryValue(query.window_days)),
    provider: normalizeQueryValue(query.provider),
    accountType: normalizeQueryValue(query.account_type),
    currentSignalKey: normalizeAllowedValue(
      normalizeQueryValue(query.current_signal_key),
      allowedCurrentSignalKeys,
    ),
    currentSignalPatternKey: normalizePatternKeyValue(normalizeQueryValue(query.current_signal_pattern_key)),
    pre401SignalKey: normalizeAllowedValue(
      normalizeQueryValue(query.pre_401_signal_key),
      allowedCurrentSignalKeys,
    ),
    pre401SignalPatternKey: normalizePatternKeyValue(normalizeQueryValue(query.pre_401_signal_pattern_key)),
    pre401GapBucket: normalizeAllowedValue(normalizeQueryValue(query.pre_401_gap_bucket), allowedPre401GapKeys),
    currentMatchLevel: normalizeAllowedValue(
      normalizeQueryValue(query.current_match_level),
      allowedCurrentMatchKeys,
    ),
    currentSignalMinStreak: normalizeAllowedValue(
      normalizeQueryValue(query.current_signal_min_streak),
      allowedCurrentSignalMinStreaks,
    ),
    currentHistoricalGapBucket: normalizeAllowedValue(
      normalizeQueryValue(query.current_historical_gap_bucket),
      allowedPre401GapKeys,
    ),
  };
}

function readCurrentRouteState(): ResearchRouteState {
  return {
    windowDays: windowDays.value,
    provider: normalizedProvider.value,
    accountType: normalizedAccountType.value,
    currentSignalKey: normalizedCurrentSignalKey.value,
    currentSignalPatternKey: normalizePatternKeyValue(normalizedCurrentSignalPatternKey.value),
    pre401SignalKey: normalizedPre401SignalKey.value,
    pre401SignalPatternKey: normalizePatternKeyValue(normalizedPre401SignalPatternKey.value),
    pre401GapBucket: normalizedPre401GapBucket.value,
    currentMatchLevel: normalizedCurrentMatchLevel.value,
    currentSignalMinStreak: normalizedCurrentSignalMinStreak.value,
    currentHistoricalGapBucket: normalizedCurrentHistoricalGapBucket.value,
  };
}

function applyRouteState(state: ResearchRouteState) {
  windowDays.value = state.windowDays;
  syncFilters({
    provider: state.provider,
    accountType: state.accountType,
    currentSignalKey: state.currentSignalKey,
    currentSignalPatternKey: state.currentSignalPatternKey,
    pre401SignalKey: state.pre401SignalKey,
    pre401SignalPatternKey: state.pre401SignalPatternKey,
    pre401GapBucket: state.pre401GapBucket,
    currentMatchLevel: state.currentMatchLevel,
    currentSignalMinStreak: state.currentSignalMinStreak,
    currentHistoricalGapBucket: state.currentHistoricalGapBucket,
  });
}

function areRouteStatesEqual(left: ResearchRouteState, right: ResearchRouteState) {
  return (
    left.windowDays === right.windowDays &&
    left.provider === right.provider &&
    left.accountType === right.accountType &&
    left.currentSignalKey === right.currentSignalKey &&
    left.currentSignalPatternKey === right.currentSignalPatternKey &&
    left.pre401SignalKey === right.pre401SignalKey &&
    left.pre401SignalPatternKey === right.pre401SignalPatternKey &&
    left.pre401GapBucket === right.pre401GapBucket &&
    left.currentMatchLevel === right.currentMatchLevel &&
    left.currentSignalMinStreak === right.currentSignalMinStreak &&
    left.currentHistoricalGapBucket === right.currentHistoricalGapBucket
  );
}

function buildRouteQuery(state: ResearchRouteState): LocationQueryRaw {
  const query: LocationQueryRaw = {};

  if (state.windowDays !== 7) {
    query.window_days = String(state.windowDays);
  }
  if (state.provider) {
    query.provider = state.provider;
  }
  if (state.accountType) {
    query.account_type = state.accountType;
  }
  if (state.currentSignalKey) {
    query.current_signal_key = state.currentSignalKey;
  }
  if (state.currentSignalPatternKey) {
    query.current_signal_pattern_key = state.currentSignalPatternKey;
  }
  if (state.pre401SignalKey) {
    query.pre_401_signal_key = state.pre401SignalKey;
  }
  if (state.pre401SignalPatternKey) {
    query.pre_401_signal_pattern_key = state.pre401SignalPatternKey;
  }
  if (state.pre401GapBucket) {
    query.pre_401_gap_bucket = state.pre401GapBucket;
  }
  if (state.currentMatchLevel) {
    query.current_match_level = state.currentMatchLevel;
  }
  if (state.currentSignalMinStreak) {
    query.current_signal_min_streak = state.currentSignalMinStreak;
  }
  if (state.currentHistoricalGapBucket) {
    query.current_historical_gap_bucket = state.currentHistoricalGapBucket;
  }

  return query;
}

function isRouteQuerySynced(query: LocationQuery, state: ResearchRouteState) {
  const targetQuery = buildRouteQuery(state);

  return researchRouteQueryKeys.every((key) => {
    const currentValue = normalizeQueryValue(query[key]);
    const targetValue = normalizeQueryValue(targetQuery[key]);
    return currentValue === targetValue;
  });
}

async function syncRouteQuery() {
  const currentState = readCurrentRouteState();

  if (isRouteQuerySynced(route.query, currentState)) {
    return;
  }

  await router.replace({
    query: buildRouteQuery(currentState),
  });
}

async function loadOverview(options?: { syncRoute?: boolean }) {
  if (options?.syncRoute !== false) {
    await syncRouteQuery();
  }

  loading.value = true;
  error.value = "";

  try {
    overview.value = await getResearchOverview({
      window_days: windowDays.value,
      provider: normalizedProvider.value || undefined,
      account_type: normalizedAccountType.value || undefined,
      current_signal_key: normalizedCurrentSignalKey.value || undefined,
      current_signal_pattern_key: normalizedCurrentSignalPatternKey.value || undefined,
      pre_401_signal_key: normalizedPre401SignalKey.value || undefined,
      pre_401_signal_pattern_key: normalizedPre401SignalPatternKey.value || undefined,
      pre_401_gap_bucket: normalizedPre401GapBucket.value || undefined,
      current_match_level: normalizedCurrentMatchLevel.value || undefined,
      current_signal_min_streak: normalizedCurrentSignalMinStreak.value
        ? Number(normalizedCurrentSignalMinStreak.value)
        : undefined,
      current_historical_gap_bucket: normalizedCurrentHistoricalGapBucket.value || undefined,
    });
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "加载研究数据失败";
  } finally {
    loading.value = false;
  }
}

function resetFilters() {
  filters.provider = "";
  filters.accountType = "";
  filters.currentSignalKey = "";
  filters.currentSignalPatternKey = "";
  filters.pre401SignalKey = "";
  filters.pre401SignalPatternKey = "";
  filters.pre401GapBucket = "";
  filters.currentMatchLevel = "";
  filters.currentSignalMinStreak = "";
  filters.currentHistoricalGapBucket = "";
  void loadOverview();
}

function bucketSummary(item: ResearchBucketCount) {
  return `${item.label}：${formatCount(item.count)} 次`;
}

function sampleUsageSummary(item: ResearchEventSample) {
  return [
    `周额度 ${formatPercent(item.previous_weekly_used_percent)}`,
    `短周期 ${formatPercent(item.previous_short_used_percent)}`,
    `remaining ${formatRemaining(item.previous_remaining)}`,
  ].join(" / ");
}

function sampleGapSummary(item: ResearchEventSample) {
  return `距 401 事件 ${formatMinutesSpan(item.previous_to_event_gap_minutes)}`;
}

function sampleSignalSummary(item: ResearchEventSample) {
  const signals: string[] = [];

  if (item.previous_limit_reached === true) {
    signals.push("limit_reached=true");
  }
  if (item.previous_allowed === false) {
    signals.push("allowed=false");
  }
  if (item.previous_status_message) {
    signals.push(`status_message=${item.previous_status_message}`);
  }

  if (!signals.length) {
    return "前序正常快照未记录明显附加信号";
  }

  return signals.join(" / ");
}

function currentSignalUsageSummary(item: ResearchCurrentSignalSample) {
  return [
    `周额度 ${formatPercent(item.current_weekly_used_percent)}`,
    `短周期 ${formatPercent(item.current_short_used_percent)}`,
    `remaining ${formatRemaining(item.current_remaining)}`,
  ].join(" / ");
}

function currentSignalPersistenceSummary(item: ResearchCurrentSignalSample) {
  const streakLabel = `连续 ${formatCount(item.consecutive_signal_snapshots)} 轮`;
  if (!item.signal_started_at) {
    return `${streakLabel}，起点未记录`;
  }

  return `${streakLabel}，起于 ${formatDateTime(item.signal_started_at)}`;
}

function currentSignalHistoricalMatchSummary(item: ResearchCurrentSignalSample) {
  const coverage = `${item.historical_match_label}（覆盖率 ${formatPercent(item.historical_match_rate)}）`;
  const segments = [coverage];

  if (item.historical_match_gap_label) {
    segments.push(`最佳历史证据 ${item.historical_match_gap_label}`);
  }
  if (item.historical_best_pattern) {
    segments.push(`最接近历史模式：${item.historical_best_pattern}`);
  }

  return segments.join("，");
}

function currentSignalHistoricalDeltaSummary(item: ResearchCurrentSignalSample | ResearchCurrentSignalGroupSample) {
  const segments: string[] = [];

  if (item.historical_overlap_signal_labels.length && item.historical_match_level !== "exact_pattern") {
    segments.push(`重合：${item.historical_overlap_signal_labels.join(" / ")}`);
  }
  if (item.historical_current_only_signal_labels.length) {
    segments.push(`当前独有：${item.historical_current_only_signal_labels.join(" / ")}`);
  }
  if (item.historical_pattern_only_signal_labels.length) {
    segments.push(`历史独有：${item.historical_pattern_only_signal_labels.join(" / ")}`);
  }

  return segments.join("；");
}

function currentSignalHistoricalReplaySummary(item: ResearchCurrentSignalSample | ResearchCurrentSignalGroupSample) {
  if (!item.historical_match_event_id || !item.historical_match_event_account_name) {
    return "";
  }

  const segments = [
    `历史样本：${item.historical_match_event_account_name}`,
    formatDateTime(item.historical_match_event_time),
  ];
  if (item.historical_match_gap_label) {
    segments.push(`前序 ${item.historical_match_gap_label}`);
  }
  return segments.join(" · ");
}

function currentGroupHistoricalLikeSummary(item: ResearchCurrentSignalGroupSample) {
  const segments = [item.historical_match_label, `连续 ${formatCount(item.consecutive_signal_snapshots)} 轮`];
  if (item.historical_match_gap_label) {
    segments.push(`前序 ${item.historical_match_gap_label}`);
  }
  return segments.join(" / ");
}

function currentGroupHistoricalGapSummary(
  item: ResearchOverviewResponse["current_signal_baseline"]["current_signal_group_breakdown"][number],
) {
  if (!item.top_historical_gap_label || item.top_historical_gap_count <= 0) {
    return "暂无高贴近历史证据";
  }
  return `${item.top_historical_gap_label} · ${formatCount(item.top_historical_gap_count)} 个样本`;
}

watch(
  () => route.query,
  (query) => {
    const nextState = buildRouteStateFromQuery(query);
    const currentState = readCurrentRouteState();

    if (!hasInitializedRouteState.value) {
      hasInitializedRouteState.value = true;
      applyRouteState(nextState);
      void loadOverview();
      return;
    }

    if (areRouteStatesEqual(nextState, currentState)) {
      return;
    }

    applyRouteState(nextState);
    void loadOverview();
  },
  { immediate: true },
);
</script>

<template>
  <section class="page-section">
    <div class="section-heading">
      <div>
        <p class="section-kicker">研究视图</p>
        <h2>围绕 401 前置信号的样本归因</h2>
      </div>
      <div class="filter-actions">
        <label>
          <span class="subtle-label">Provider</span>
          <input
            v-model="filters.provider"
            class="input-field"
            placeholder="例如 openai"
            @keyup.enter="loadOverview"
          />
        </label>
        <label>
          <span class="subtle-label">类型</span>
          <input
            v-model="filters.accountType"
            class="input-field"
            placeholder="例如 chatgpt"
            @keyup.enter="loadOverview"
          />
        </label>
        <label>
          <span class="subtle-label">当前信号</span>
          <select v-model="filters.currentSignalKey" class="input-field compact-select" @change="loadOverview">
            <option value="">全部信号</option>
            <option v-for="item in CURRENT_SIGNAL_OPTIONS" :key="item.key" :value="item.key">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          <span class="subtle-label">当前模式</span>
          <select v-model="filters.currentSignalPatternKey" class="input-field compact-select" @change="loadOverview">
            <option value="">全部组合</option>
            <option v-for="item in currentSignalPatternOptions" :key="`current-pattern-${item.key}`" :value="item.key">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          <span class="subtle-label">前序信号</span>
          <select v-model="filters.pre401SignalKey" class="input-field compact-select" @change="loadOverview">
            <option value="">全部信号</option>
            <option v-for="item in CURRENT_SIGNAL_OPTIONS" :key="`pre-${item.key}`" :value="item.key">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          <span class="subtle-label">前序模式</span>
          <select v-model="filters.pre401SignalPatternKey" class="input-field compact-select" @change="loadOverview">
            <option value="">全部组合</option>
            <option v-for="item in pre401SignalPatternOptions" :key="`pre-pattern-${item.key}`" :value="item.key">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          <span class="subtle-label">前序新鲜度</span>
          <select v-model="filters.pre401GapBucket" class="input-field compact-select" @change="loadOverview">
            <option value="">全部区间</option>
            <option v-for="item in PRE_401_GAP_OPTIONS" :key="item.key" :value="item.key">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          <span class="subtle-label">历史贴近</span>
          <select v-model="filters.currentMatchLevel" class="input-field compact-select" @change="loadOverview">
            <option value="">全部贴近度</option>
            <option v-for="item in CURRENT_MATCH_OPTIONS" :key="item.key" :value="item.key">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          <span class="subtle-label">连续轮数</span>
          <select v-model="filters.currentSignalMinStreak" class="input-field compact-select" @change="loadOverview">
            <option value="">全部</option>
            <option v-for="item in CURRENT_STREAK_OPTIONS" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          <span class="subtle-label">最佳历史证据</span>
          <select
            v-model="filters.currentHistoricalGapBucket"
            class="input-field compact-select"
            @change="loadOverview"
          >
            <option value="">全部区间</option>
            <option v-for="item in PRE_401_GAP_OPTIONS" :key="`current-gap-${item.key}`" :value="item.key">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          <span class="subtle-label">窗口</span>
          <select v-model="windowDays" class="input-field compact-select" @change="loadOverview">
            <option :value="7">最近 7 天</option>
            <option :value="14">最近 14 天</option>
            <option :value="30">最近 30 天</option>
          </select>
        </label>
        <button v-if="hasScopedFilters" class="ghost-button" type="button" @click="resetFilters">清空筛选</button>
        <button class="ghost-button" type="button" @click="loadOverview">刷新</button>
      </div>
    </div>

    <p class="subtle-line">当前研究范围：{{ scopeSummary }}</p>
    <p class="subtle-line">当前筛选会写入页面 URL，刷新或复制链接后可直接恢复这组研究视角。</p>
    <p v-if="selectedCurrentSignalLabel || selectedCurrentSignalPatternLabel" class="subtle-line">
      “当前信号 / 当前模式”筛选只作用于“当前基线”“当前组合热点”和“当前样本”区块；历史 401 统计仍按 provider / 类型 / 时间窗口聚合。
    </p>
    <p
      v-if="selectedCurrentMatchLabel || selectedCurrentSignalMinStreakLabel || selectedCurrentHistoricalGapBucketLabel"
      class="subtle-line"
    >
      “历史贴近 / 连续轮数 / 最佳历史证据”筛选也只作用于“当前基线”“当前组合热点”和“当前样本”区块，用来优先定位更值得继续回放的当前非 401 样本。
    </p>
    <p v-if="selectedPre401SignalLabel || selectedPre401SignalPatternLabel" class="subtle-line">
      “前序信号 / 前序模式”筛选只作用于“前序信号”“周/短周期分桶”和“最近 401 样本”区块；顶部摘要、小时分布与组合热点仍按 provider / 类型 / 时间窗口聚合。
    </p>
    <p v-if="selectedPre401GapBucketLabel" class="subtle-line">
      “前序新鲜度”筛选同样只收窄历史证据区，用来区分更贴近 401 事件的高可信前序样本和间隔过长的弱证据。
    </p>
    <p
      v-if="
        selectedCurrentSignalLabel ||
        selectedCurrentSignalPatternLabel ||
        selectedPre401SignalLabel ||
        selectedPre401SignalPatternLabel ||
        selectedPre401GapBucketLabel
      "
      class="subtle-line"
    >
      “信号对照”和“组合对照”区块只受 provider / 类型 / 时间窗口影响，不跟随“当前信号 / 当前模式 / 前序信号 / 前序模式 / 前序新鲜度”局部收窄，便于稳定比较历史样本与当前基线。
    </p>
    <p v-if="error" class="feedback error">{{ error }}</p>
    <p v-else-if="loading && !overview" class="feedback">正在读取研究聚合...</p>

    <template v-if="overview">
      <div class="metric-grid">
        <MetricCard label="窗口内 401 事件" :value="formatCount(overview.summary.became_401_events)" accent="sun" />
        <MetricCard label="受影响账号" :value="formatCount(overview.summary.affected_accounts)" accent="rose" />
        <MetricCard label="当前 401 账号" :value="formatCount(overview.summary.current_401_accounts)" accent="ink" />
        <MetricCard label="当前 401 率" :value="formatPercent(overview.summary.current_401_rate)" accent="teal" />
        <MetricCard label="活跃账号" :value="formatCount(overview.summary.active_accounts)" />
        <MetricCard label="可回放前序样本" :value="formatCount(overview.summary.sampled_previous_snapshots)" hint="存在 previous snapshot" />
        <MetricCard
          label="当前研究信号账号"
          :value="formatCount(overview.current_signal_baseline.signal_accounts)"
          hint="当前非 401 且仍可继续观察"
        />
      </div>

      <p v-if="overview.summary.became_401_events === 0" class="feedback">
        {{ hasScopedFilters ? "当前筛选范围内" : "当前历史库里" }} 还没有 `became_401` 事件。下面展示的是仍为非 `401` 账号的研究信号基线，只用于后续样本积累，不代表账号异常。
      </p>

      <div class="panel-grid">
        <article class="panel chart-panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">小时分布</p>
              <h3>401 更集中在哪些时段</h3>
            </div>
          </div>
          <DistributionBarChart :labels="hourlyLabels" :values="hourlyValues" series-name="401 事件数" />
        </article>

        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">前序信号</p>
              <h3>401 前最后一次正常快照里出现过什么</h3>
            </div>
          </div>

          <div class="detail-list">
            <div class="detail-row">
              <span>研究窗口</span>
              <strong>{{ overview.window_days }} 天</strong>
            </div>
            <div class="detail-row">
              <span>窗口内 401 事件</span>
              <strong>{{ formatCount(overview.pre_401_insights.sampled_events) }}</strong>
            </div>
            <div class="detail-row">
              <span>带前序样本的事件</span>
              <strong>{{ formatCount(overview.pre_401_insights.events_with_previous_snapshot) }}</strong>
            </div>
            <div class="detail-row">
              <span>受影响组合</span>
              <strong>{{ formatCount(overview.summary.affected_provider_groups) }}</strong>
            </div>
          </div>

          <div class="signal-chip-grid">
            <div
              v-for="item in overview.pre_401_insights.signal_breakdown"
              :key="item.key"
              class="signal-chip signal-chip-action"
            >
              <span>{{ bucketSummary(item) }}</span>
              <button
                class="ghost-button compact-button mini-action-button"
                type="button"
                :disabled="isPre401SignalFilterActive(item.key)"
                @click="applyPre401SignalFilter(item.key)"
              >
                {{ isPre401SignalFilterActive(item.key) ? "已筛到前序信号" : "筛到前序信号" }}
              </button>
            </div>
          </div>

          <p v-if="dominantPre401SignalPatternSummary" class="subtle-line">
            {{ dominantPre401SignalPatternSummary }}
          </p>

          <div
            v-if="
              overview.pre_401_insights.signal_pattern_breakdown.length ||
              overview.pre_401_insights.top_status_messages.length
            "
            class="observation-list"
          >
            <p v-if="overview.pre_401_insights.signal_pattern_breakdown.length" class="subtle-label">高频前序信号组合</p>
            <div
              v-for="item in overview.pre_401_insights.signal_pattern_breakdown"
              :key="`pre-pattern-${item.key}`"
              class="observation-item observation-item-action"
            >
              <span>{{ item.label }} · {{ formatCount(item.count) }} 次</span>
              <button
                class="ghost-button compact-button mini-action-button"
                type="button"
                :disabled="isPre401SignalPatternFilterActive(item.key)"
                @click="applyPre401SignalPatternFilter(item.key)"
              >
                {{ isPre401SignalPatternFilterActive(item.key) ? "已筛到前序模式" : "筛到前序模式" }}
              </button>
            </div>

            <p v-if="overview.pre_401_insights.top_status_messages.length" class="subtle-label">高频 status_message</p>
            <p
              v-for="item in overview.pre_401_insights.top_status_messages"
              :key="`pre-status-${item.key}`"
              class="observation-item"
            >
              {{ item.label }} · {{ formatCount(item.count) }} 次
            </p>
          </div>
          <p v-else class="feedback">当前窗口和筛选范围内，前序正常样本还没有留下稳定的组合模式或 `status_message`。</p>
        </article>
      </div>

      <div class="panel-grid">
        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">当前基线</p>
              <h3>仍正常账号里已经出现了哪些研究信号</h3>
            </div>
          </div>

          <div class="detail-list">
            <div class="detail-row">
              <span>当前可观测账号</span>
              <strong>{{ formatCount(overview.current_signal_baseline.observed_accounts) }}</strong>
            </div>
            <div class="detail-row">
              <span>出现研究信号的账号</span>
              <strong>{{ formatCount(overview.current_signal_baseline.signal_accounts) }}</strong>
            </div>
          </div>

          <p v-if="currentSignalScopeHint" class="subtle-line">
            {{ currentSignalScopeHint }}
          </p>

          <p v-if="dominantCurrentSignalPatternSummary" class="subtle-line">
            {{ dominantCurrentSignalPatternSummary }}
          </p>
          <p v-if="leadingHistoricalMatchSummary" class="subtle-line">
            {{ leadingHistoricalMatchSummary }}
          </p>

          <div v-if="overview.current_signal_baseline.signal_breakdown.length" class="signal-chip-grid">
            <div
              v-for="item in overview.current_signal_baseline.signal_breakdown"
              :key="item.key"
              class="signal-chip signal-chip-action"
            >
              <span>{{ bucketSummary(item) }}</span>
              <button
                class="ghost-button compact-button mini-action-button"
                type="button"
                :disabled="isCurrentSignalFilterActive(item.key)"
                @click="applyCurrentSignalFilter(item.key)"
              >
                {{ isCurrentSignalFilterActive(item.key) ? "已筛到当前信号" : "筛到当前信号" }}
              </button>
            </div>
          </div>
          <p v-else class="feedback">当前筛选范围内仍为非 `401` 的账号里，还没有留下需要继续跟踪的研究信号。</p>

          <div v-if="overview.current_signal_baseline.signal_streak_breakdown.length" class="observation-list">
            <p class="subtle-label">连续性分布</p>
            <p
              v-for="item in overview.current_signal_baseline.signal_streak_breakdown"
              :key="`streak-${item.key}`"
              class="observation-item"
            >
              {{ item.label }} · {{ formatCount(item.count) }} 个账号
            </p>
          </div>

          <div v-if="overview.current_signal_baseline.historical_match_breakdown.length" class="observation-list">
            <p class="subtle-label">与历史 401 前样本的贴近程度</p>
            <div
              v-for="item in overview.current_signal_baseline.historical_match_breakdown"
              :key="`historical-match-${item.key}`"
              class="observation-item observation-item-action"
            >
              <span>{{ item.label }} · {{ formatCount(item.count) }} 个账号</span>
              <button
                class="ghost-button compact-button mini-action-button"
                type="button"
                :disabled="isCurrentMatchLevelFilterActive(item.key)"
                @click="applyCurrentMatchLevelFilter(item.key)"
              >
                {{ isCurrentMatchLevelFilterActive(item.key) ? "已筛到贴近度" : "筛到贴近度" }}
              </button>
            </div>
          </div>

          <div
            v-if="overview.current_signal_baseline.historical_match_gap_breakdown.some((item) => item.count > 0)"
            class="observation-list"
          >
            <p class="subtle-label">最佳历史证据新鲜度</p>
            <div
              v-for="item in overview.current_signal_baseline.historical_match_gap_breakdown.filter((entry) => entry.count > 0)"
              :key="`historical-gap-${item.key}`"
              class="observation-item observation-item-action"
            >
              <span>{{ item.label }} · {{ formatCount(item.count) }} 个账号</span>
              <button
                class="ghost-button compact-button mini-action-button"
                type="button"
                :disabled="isCurrentHistoricalGapBucketFilterActive(item.key)"
                @click="applyCurrentHistoricalGapBucketFilter(item.key)"
              >
                {{
                  isCurrentHistoricalGapBucketFilterActive(item.key) ? "已筛到最佳历史证据" : "筛到最佳历史证据"
                }}
              </button>
            </div>
          </div>

          <div
            v-if="
              overview.current_signal_baseline.signal_pattern_breakdown.length ||
              overview.current_signal_baseline.top_status_messages.length
            "
            class="observation-list"
          >
            <p
              v-if="overview.current_signal_baseline.signal_pattern_breakdown.length"
              class="subtle-label"
            >
              高频信号组合
            </p>
            <div
              v-for="item in overview.current_signal_baseline.signal_pattern_breakdown"
              :key="`pattern-${item.key}`"
              class="observation-item observation-item-action"
            >
              <span>{{ item.label }} · {{ formatCount(item.count) }} 个账号</span>
              <button
                class="ghost-button compact-button mini-action-button"
                type="button"
                :disabled="isCurrentSignalPatternFilterActive(item.key)"
                @click="applyCurrentSignalPatternFilter(item.key)"
              >
                {{ isCurrentSignalPatternFilterActive(item.key) ? "已筛到当前模式" : "筛到当前模式" }}
              </button>
            </div>

            <p
              v-if="overview.current_signal_baseline.top_status_messages.length"
              class="subtle-label"
            >
              高频 status_message
            </p>
            <p
              v-for="item in overview.current_signal_baseline.top_status_messages"
              :key="`status-${item.key}`"
              class="observation-item"
            >
              {{ item.label }} · {{ formatCount(item.count) }} 个账号
            </p>
          </div>
        </article>
      </div>

      <article class="panel">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">信号对照</p>
            <h3>历史 401 前信号与当前基线谁更集中</h3>
          </div>
        </div>

        <p v-if="leadingSignalComparisonSummary" class="subtle-line">
          {{ leadingSignalComparisonSummary }}
        </p>
        <p v-else-if="!hasHistoricalPreviousSamples" class="subtle-line">
          当前范围内还没有可回放的历史 `401` 前样本，信号对照会在出现前序证据后自动启用；现阶段请优先观察“当前基线”和“当前组合热点”。
        </p>
        <p v-else class="subtle-line">
          当前范围内还没有出现“历史命中率明显高于当前基线”的单一信号，需结合组合模式与样本回放继续判断。
        </p>

        <div v-if="overview.signal_comparison.length" class="table-wrap">
          <table class="data-table compact">
            <thead>
              <tr>
                <th>信号</th>
                <th>历史前序样本</th>
                <th>历史命中率</th>
                <th>当前基线账号</th>
                <th>当前命中率</th>
                <th>历史-当前</th>
                <th>下钻</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in overview.signal_comparison" :key="`signal-comparison-${item.key}`">
                <td>
                  <strong>{{ item.label }}</strong>
                </td>
                <td>{{ formatCount(item.pre_401_count) }}</td>
                <td>{{ formatPercent(item.pre_401_rate) }}</td>
                <td>{{ formatCount(item.current_count) }}</td>
                <td>{{ formatPercent(item.current_rate) }}</td>
                <td>{{ formatPercent(item.rate_gap) }}</td>
                <td class="table-action-cell">
                  <div class="table-action-stack">
                    <button
                      class="ghost-button compact-button mini-action-button"
                      type="button"
                      :disabled="isCurrentSignalFilterActive(item.key)"
                      @click="applyCurrentSignalFilter(item.key)"
                    >
                      当前
                    </button>
                    <button
                      class="ghost-button compact-button mini-action-button"
                      type="button"
                      :disabled="isPre401SignalFilterActive(item.key)"
                      @click="applyPre401SignalFilter(item.key)"
                    >
                      前序
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">组合对照</p>
            <h3>历史 401 前组合模式与当前基线谁更接近</h3>
          </div>
        </div>

        <p v-if="leadingSignalPatternComparisonSummary" class="subtle-line">
          {{ leadingSignalPatternComparisonSummary }}
        </p>
        <p v-else-if="!hasHistoricalPreviousSamples" class="subtle-line">
          当前范围内还没有可回放的历史 `401` 前样本，组合对照暂时没有研究基线；等出现真实前序样本后再看哪些组合更像历史证据。
        </p>
        <p v-else class="subtle-line">
          当前范围内还没有出现“历史命中率明显高于当前基线”的组合模式，需继续积累样本或结合单信号差值判断。
        </p>

        <div v-if="overview.signal_pattern_comparison.length" class="table-wrap">
          <table class="data-table compact">
            <thead>
              <tr>
                <th>组合模式</th>
                <th>历史前序样本</th>
                <th>历史命中率</th>
                <th>当前基线账号</th>
                <th>当前命中率</th>
                <th>历史-当前</th>
                <th>下钻</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in overview.signal_pattern_comparison" :key="`signal-pattern-comparison-${item.key}`">
                <td>
                  <strong>{{ item.label }}</strong>
                </td>
                <td>{{ formatCount(item.pre_401_count) }}</td>
                <td>{{ formatPercent(item.pre_401_rate) }}</td>
                <td>{{ formatCount(item.current_count) }}</td>
                <td>{{ formatPercent(item.current_rate) }}</td>
                <td>{{ formatPercent(item.rate_gap) }}</td>
                <td class="table-action-cell">
                  <div class="table-action-stack">
                    <button
                      class="ghost-button compact-button mini-action-button"
                      type="button"
                      :disabled="isCurrentSignalPatternFilterActive(item.key)"
                      @click="applyCurrentSignalPatternFilter(item.key)"
                    >
                      当前
                    </button>
                    <button
                      class="ghost-button compact-button mini-action-button"
                      type="button"
                      :disabled="isPre401SignalPatternFilterActive(item.key)"
                      @click="applyPre401SignalPatternFilter(item.key)"
                    >
                      前序
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <div class="panel-grid research-band-grid">
        <article class="panel chart-panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">证据新鲜度</p>
              <h3>前序正常快照距离 401 有多近</h3>
            </div>
          </div>
          <DistributionBarChart :labels="gapBandLabels" :values="gapBandValues" series-name="前序样本数" />
          <div v-if="overview.pre_401_insights.previous_to_event_gap_bands.length" class="observation-list">
            <div
              v-for="item in overview.pre_401_insights.previous_to_event_gap_bands"
              :key="`gap-band-${item.key}`"
              class="observation-item observation-item-action"
            >
              <span>{{ item.label }} · {{ formatCount(item.count) }} 次</span>
              <button
                class="ghost-button compact-button mini-action-button"
                type="button"
                :disabled="isPre401GapBucketFilterActive(item.key)"
                @click="applyPre401GapBucketFilter(item.key)"
              >
                {{ isPre401GapBucketFilterActive(item.key) ? "已筛到新鲜度" : "筛到新鲜度" }}
              </button>
            </div>
          </div>
        </article>

        <article class="panel chart-panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">周额度样本</p>
              <h3>401 前最后一次周额度分桶</h3>
            </div>
          </div>
          <DistributionBarChart :labels="weeklyBandLabels" :values="weeklyBandValues" series-name="周额度样本数" />
        </article>

        <article class="panel chart-panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">短周期样本</p>
              <h3>401 前最后一次短周期额度分桶</h3>
            </div>
          </div>
          <DistributionBarChart :labels="shortBandLabels" :values="shortBandValues" series-name="短周期样本数" />
        </article>
      </div>

      <article class="panel">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">组合研究</p>
            <h3>Provider + 类型组合的 401 热点</h3>
          </div>
        </div>

        <div v-if="overview.provider_account_type_breakdown.length" class="table-wrap">
          <table class="data-table compact">
            <thead>
              <tr>
                <th>组合</th>
                <th>当前账号</th>
                <th>当前 401</th>
                <th>401 率</th>
                <th>窗口内 401</th>
                <th>受影响账号</th>
                <th>最近一次</th>
                <th>范围</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in overview.provider_account_type_breakdown" :key="item.label">
                <td>
                  <strong>{{ item.label }}</strong>
                  <p class="subtle-line">
                    provider={{ item.provider ?? "未标记" }} / type={{ item.account_type ?? "未标记" }}
                  </p>
                </td>
                <td>{{ formatCount(item.total_accounts) }}</td>
                <td>{{ formatCount(item.current_401_accounts) }}</td>
                <td>{{ formatPercent(item.current_401_rate) }}</td>
                <td>{{ formatCount(item.became_401_events) }}</td>
                <td>{{ formatCount(item.affected_accounts) }}</td>
                <td>{{ formatDateTime(item.last_became_401_at) }}</td>
                <td class="table-action-cell">
                  <button
                    class="ghost-button compact-button mini-action-button"
                    type="button"
                    :disabled="isScopeFilterActive(item.provider, item.account_type)"
                    @click="applyScopeFilter(item.provider, item.account_type)"
                  >
                    {{ isScopeFilterActive(item.provider, item.account_type) ? "已应用组合" : "应用组合" }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="feedback">当前窗口和筛选范围内还没有可供研究的组合样本。</p>
      </article>

      <article class="panel">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">当前组合热点</p>
            <h3>哪些 Provider + 类型组合正在积累研究信号</h3>
          </div>
        </div>

        <p v-if="leadingHistoricalLikeGroupSummary" class="subtle-line">
          {{ leadingHistoricalLikeGroupSummary }}
        </p>
        <p v-if="hasHistoricalPreviousSamples" class="subtle-line">
          “历史高贴近”只统计与历史 `401` 前模式“完全同模式”或“被历史模式覆盖”的当前样本；若数量相同，会优先把命中过更近历史证据的组合排在前面。
        </p>
        <p v-else class="subtle-line">
          当前范围内还没有历史 `401` 前样本，因此“历史高贴近”列会先保持为 `0`；现阶段更适合先按信号规模、连续轮数和主导模式积累样本。
        </p>

        <div v-if="overview.current_signal_baseline.current_signal_group_breakdown.length" class="table-wrap">
          <table class="data-table compact">
            <thead>
              <tr>
                <th>组合</th>
                <th>可观测账号</th>
                <th>信号账号</th>
                <th>信号率</th>
                <th>连续 2 轮+</th>
                <th>历史高贴近</th>
                <th>最佳历史证据</th>
                <th>高贴近样本</th>
                <th>主导模式</th>
                <th>下钻</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in overview.current_signal_baseline.current_signal_group_breakdown"
                :key="`current-group-${item.label}`"
              >
                <td>
                  <strong>{{ item.label }}</strong>
                  <p class="subtle-line">
                    provider={{ item.provider ?? "未标记" }} / type={{ item.account_type ?? "未标记" }}
                  </p>
                </td>
                <td>{{ formatCount(item.observed_accounts) }}</td>
                <td>{{ formatCount(item.signal_accounts) }}</td>
                <td>{{ formatPercent(item.signal_rate) }}</td>
                <td>{{ formatCount(item.multi_round_signal_accounts) }}</td>
                <td>
                  {{ formatCount(item.historical_like_accounts) }}
                  <p class="subtle-line">{{ formatPercent(item.historical_like_rate) }}</p>
                </td>
                <td>
                  <p>{{ currentGroupHistoricalGapSummary(item) }}</p>
                  <p v-if="item.top_historical_gap_label" class="subtle-line">
                    仅统计历史高贴近样本命中的最佳历史证据
                  </p>
                </td>
                <td>
                  <div v-if="item.top_historical_like_samples.length" class="observation-list compact-observations">
                    <div
                      v-for="sample in item.top_historical_like_samples"
                      :key="`current-group-sample-${item.label}-${sample.account_id}`"
                    >
                      <RouterLink class="inline-link" :to="`/accounts/${sample.account_id}`">
                        {{ sample.account_name }}
                      </RouterLink>
                      <p class="subtle-line">{{ currentGroupHistoricalLikeSummary(sample) }}</p>
                      <p v-if="sample.historical_best_pattern" class="subtle-line">
                        最接近：{{ sample.historical_best_pattern }}
                      </p>
                      <p v-if="currentSignalHistoricalDeltaSummary(sample)" class="subtle-line">
                        {{ currentSignalHistoricalDeltaSummary(sample) }}
                      </p>
                      <p v-if="sample.historical_match_event_id" class="subtle-line">
                        <RouterLink class="inline-link" :to="`/events/${sample.historical_match_event_id}`">
                          {{ currentSignalHistoricalReplaySummary(sample) }}
                        </RouterLink>
                      </p>
                    </div>
                  </div>
                  <p v-else class="subtle-line">暂无高贴近样本</p>
                </td>
                <td>{{ item.top_signal_pattern ?? "未归纳" }}</td>
                <td class="table-action-cell">
                  <div class="table-action-stack">
                    <button
                      class="ghost-button compact-button mini-action-button"
                      type="button"
                      :disabled="isScopeFilterActive(item.provider, item.account_type)"
                      @click="applyScopeFilter(item.provider, item.account_type)"
                    >
                      组合
                    </button>
                    <button
                      v-if="item.top_historical_gap_bucket"
                      class="ghost-button compact-button mini-action-button"
                      type="button"
                      :disabled="isCurrentHistoricalGapBucketFilterActive(item.top_historical_gap_bucket)"
                      @click="applyCurrentHistoricalGapBucketFilter(item.top_historical_gap_bucket)"
                    >
                      历史证据
                    </button>
                    <button
                      v-if="item.top_signal_pattern_key"
                      class="ghost-button compact-button mini-action-button"
                      type="button"
                      :disabled="isCurrentSignalPatternFilterActive(item.top_signal_pattern_key)"
                      @click="applyCurrentSignalPatternFilter(item.top_signal_pattern_key)"
                    >
                      主导模式
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="feedback">当前筛选范围内还没有出现可归纳的当前研究信号组合。</p>
      </article>

      <article class="panel">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">样本证据</p>
            <h3>最近进入 401 的真实样本</h3>
          </div>
        </div>

        <div v-if="overview.recent_event_samples.length" class="event-stack">
          <article
            v-for="sample in overview.recent_event_samples"
            :key="sample.event_id"
            class="event-card"
          >
            <div class="event-card-head">
              <div>
                <p class="event-type">became_401</p>
                <RouterLink class="inline-link event-title" :to="`/events/${sample.event_id}`">
                  {{ sample.account_name }}
                </RouterLink>
                <p class="subtle-line">
                  {{ sample.provider ?? "未标记 provider" }} / {{ sample.account_type ?? "未标记类型" }}
                </p>
              </div>
              <div class="status-stack">
                <StatusPill
                  :tone="sample.current_is_401 ? 'danger' : 'success'"
                  :text="sample.current_is_401 ? '当前仍为 401' : '当前已恢复'"
                />
                <RouterLink class="nav-tab compact-button" :to="`/accounts/${sample.account_id}`">
                  查看账号
                </RouterLink>
              </div>
            </div>

            <div class="event-grid">
              <div>
                <p class="subtle-label">事件时间</p>
                <p>{{ formatDateTime(sample.event_time) }}</p>
              </div>
              <div>
                <p class="subtle-label">前序正常快照</p>
                <p>{{ formatDateTime(sample.previous_checked_at) }}</p>
                <p class="subtle-line">{{ sampleGapSummary(sample) }}</p>
                <p class="subtle-line">{{ sampleUsageSummary(sample) }}</p>
              </div>
              <div>
                <p class="subtle-label">前序附加信号</p>
                <p>{{ sampleSignalSummary(sample) }}</p>
              </div>
            </div>
          </article>
        </div>
        <p v-else class="feedback">当前窗口和筛选范围内还没有最近 401 样本可回放。</p>
      </article>

      <article class="panel">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">当前样本</p>
            <h3>仍正常但值得持续观察的账号</h3>
          </div>
        </div>

        <div v-if="overview.current_signal_baseline.recent_samples.length" class="event-stack">
          <article
            v-for="sample in overview.current_signal_baseline.recent_samples"
            :key="sample.account_id"
            class="event-card"
          >
            <div class="event-card-head">
              <div>
                <p class="event-type">current_signal</p>
                <RouterLink class="inline-link event-title" :to="`/accounts/${sample.account_id}`">
                  {{ sample.account_name }}
                </RouterLink>
                <p class="subtle-line">
                  {{ sample.provider ?? "未标记 provider" }} / {{ sample.account_type ?? "未标记类型" }}
                </p>
              </div>
              <div class="status-stack">
                <StatusPill tone="success" text="当前非 401" />
                <p class="subtle-line">最近检测：{{ formatDateTime(sample.current_last_checked_at) }}</p>
              </div>
            </div>

            <div class="event-grid">
              <div>
                <p class="subtle-label">当前额度/余量</p>
                <p>{{ currentSignalUsageSummary(sample) }}</p>
              </div>
              <div>
                <p class="subtle-label">已观测信号</p>
                <p class="subtle-line">{{ currentSignalPersistenceSummary(sample) }}</p>
                <p class="subtle-line">{{ currentSignalHistoricalMatchSummary(sample) }}</p>
                <p v-if="currentSignalHistoricalDeltaSummary(sample)" class="subtle-line">
                  {{ currentSignalHistoricalDeltaSummary(sample) }}
                </p>
                <p v-if="sample.historical_match_event_id" class="subtle-line">
                  <RouterLink class="inline-link" :to="`/events/${sample.historical_match_event_id}`">
                    {{ currentSignalHistoricalReplaySummary(sample) }}
                  </RouterLink>
                </p>
                <div class="signal-chip-grid">
                  <div
                    v-for="label in sample.signal_labels"
                    :key="`${sample.account_id}-${label}`"
                    class="signal-chip"
                  >
                    {{ label }}
                  </div>
                </div>
              </div>
              <div>
                <p class="subtle-label">status_message 摘要</p>
                <p>{{ sample.status_message_excerpt ?? "未记录" }}</p>
              </div>
            </div>
          </article>
        </div>
        <p v-else class="feedback">当前筛选范围内没有需要额外追踪的非 `401` 研究样本。</p>
      </article>
    </template>
  </section>
</template>
