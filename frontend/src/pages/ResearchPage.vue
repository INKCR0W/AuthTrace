<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { RouterLink } from "vue-router";

import { getResearchOverview } from "@/api/client";
import DistributionBarChart from "@/components/DistributionBarChart.vue";
import MetricCard from "@/components/MetricCard.vue";
import StatusPill from "@/components/StatusPill.vue";
import { formatCount, formatDateTime, formatMinutesSpan, formatPercent, formatRemaining } from "@/lib/format";
import type {
  ResearchBucketCount,
  ResearchCurrentSignalSample,
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
const currentSignalLabelMap = Object.fromEntries(
  CURRENT_SIGNAL_OPTIONS.map((item) => [item.key, item.label]),
) as Record<string, string>;

const loading = ref(false);
const error = ref("");
const windowDays = ref(7);
const overview = ref<ResearchOverviewResponse | null>(null);
const filters = reactive({
  provider: "",
  accountType: "",
  currentSignalKey: "",
  pre401SignalKey: "",
});

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
const normalizedPre401SignalKey = computed(() => filters.pre401SignalKey.trim());
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
const hasScopedFilters = computed(
  () =>
    Boolean(
      normalizedProvider.value ||
        normalizedAccountType.value ||
        normalizedCurrentSignalKey.value ||
        normalizedPre401SignalKey.value,
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
  if (selectedPre401SignalLabel.value) {
    segments.push(`前序信号=${selectedPre401SignalLabel.value}`);
  }

  return segments.length ? segments.join(" / ") : "全部账号";
});
const currentSignalScopeHint = computed(() => {
  if (!selectedCurrentSignalLabel.value) {
    return "";
  }
  return `当前基线已按“${selectedCurrentSignalLabel.value}”收窄；下方仍会继续展示这些样本共现的其他信号，便于判断伴随模式。`;
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

async function loadOverview() {
  loading.value = true;
  error.value = "";

  try {
    overview.value = await getResearchOverview({
      window_days: windowDays.value,
      provider: normalizedProvider.value || undefined,
      account_type: normalizedAccountType.value || undefined,
      current_signal_key: normalizedCurrentSignalKey.value || undefined,
      pre_401_signal_key: normalizedPre401SignalKey.value || undefined,
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
  filters.pre401SignalKey = "";
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
  if (!item.historical_best_pattern) {
    return coverage;
  }

  return `${coverage}，最接近历史模式：${item.historical_best_pattern}`;
}

onMounted(() => {
  void loadOverview();
});
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
          <span class="subtle-label">前序信号</span>
          <select v-model="filters.pre401SignalKey" class="input-field compact-select" @change="loadOverview">
            <option value="">全部信号</option>
            <option v-for="item in CURRENT_SIGNAL_OPTIONS" :key="`pre-${item.key}`" :value="item.key">
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
    <p v-if="selectedCurrentSignalLabel" class="subtle-line">
      “当前信号”筛选只作用于“当前基线”“当前组合热点”和“当前样本”区块；历史 401 统计仍按 provider / 类型 / 时间窗口聚合。
    </p>
    <p v-if="selectedPre401SignalLabel" class="subtle-line">
      “前序信号”筛选只作用于“前序信号”“周/短周期分桶”和“最近 401 样本”区块；顶部摘要、小时分布与组合热点仍按 provider / 类型 / 时间窗口聚合。
    </p>
    <p v-if="selectedCurrentSignalLabel || selectedPre401SignalLabel" class="subtle-line">
      “信号对照”和“组合对照”区块只受 provider / 类型 / 时间窗口影响，不跟随“当前信号 / 前序信号”下拉局部收窄，便于稳定比较历史样本与当前基线。
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
              class="signal-chip"
            >
              {{ bucketSummary(item) }}
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
            <p
              v-for="item in overview.pre_401_insights.signal_pattern_breakdown"
              :key="`pre-pattern-${item.key}`"
              class="observation-item"
            >
              {{ item.label }} · {{ formatCount(item.count) }} 次
            </p>

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
              class="signal-chip"
            >
              {{ bucketSummary(item) }}
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
            <p
              v-for="item in overview.current_signal_baseline.historical_match_breakdown"
              :key="`historical-match-${item.key}`"
              class="observation-item"
            >
              {{ item.label }} · {{ formatCount(item.count) }} 个账号
            </p>
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
            <p
              v-for="item in overview.current_signal_baseline.signal_pattern_breakdown"
              :key="`pattern-${item.key}`"
              class="observation-item"
            >
              {{ item.label }} · {{ formatCount(item.count) }} 个账号
            </p>

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

        <div v-if="overview.current_signal_baseline.current_signal_group_breakdown.length" class="table-wrap">
          <table class="data-table compact">
            <thead>
              <tr>
                <th>组合</th>
                <th>可观测账号</th>
                <th>信号账号</th>
                <th>信号率</th>
                <th>连续 2 轮+</th>
                <th>主导模式</th>
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
                <td>{{ item.top_signal_pattern ?? "未归纳" }}</td>
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
