<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { getAccountDetail } from "@/api/client";
import AccountUsageChart from "@/components/AccountUsageChart.vue";
import CohortRiskTrendChart from "@/components/CohortRiskTrendChart.vue";
import StatusPill from "@/components/StatusPill.vue";
import { formatCount, formatDateTime, formatPercent, formatRemaining, formatStatusCode } from "@/lib/format";
import type {
  AccountCohortBreakdown,
  AccountDetailResponse,
  AccountEventSummary,
  AccountRiskSignal,
  AccountSnapshotSummary,
} from "@/types/api";


const route = useRoute();
const loading = ref(false);
const error = ref("");
const detail = ref<AccountDetailResponse | null>(null);

const accountId = computed(() => Number(route.params.accountId));
const recentSnapshots = computed(() => detail.value?.recent_snapshots ?? []);
const chartSnapshots = computed(() => [...recentSnapshots.value].reverse());
const snapshotById = computed(() => new Map(recentSnapshots.value.map((snapshot) => [snapshot.id, snapshot])));
const riskSignals = computed(() => detail.value?.risk_overview.signals ?? []);
const providerTrendPoints = computed(() => detail.value?.provider_account_type_trend ?? []);

const summaryCards = computed(() => {
  const snapshots = recentSnapshots.value;
  const failed = snapshots.filter((snapshot) => snapshot.snapshot_status !== "success");
  const current401 = snapshots.filter((snapshot) => snapshot.is_401);

  return [
    {
      label: "样本窗口",
      value: `${snapshots.length} 次`,
      hint: "当前详情接口返回的最近快照数",
      tone: "muted" as const,
    },
    {
      label: "当前 401 样本",
      value: `${current401.length} 次`,
      hint: current401[0] ? `最近一次 ${formatDateTime(current401[0].checked_at)}` : "窗口内没有 401 快照",
      tone: current401.length > 0 ? "danger" as const : "success" as const,
    },
    {
      label: "失败快照",
      value: `${failed.length} 次`,
      hint: failed[0] ? `最近一次失败 ${formatDateTime(failed[0].checked_at)}` : "窗口内没有失败快照",
      tone: failed.length > 0 ? "warning" as const : "success" as const,
    },
  ];
});

const eventTransitions = computed(() => (detail.value?.recent_events ?? []).map((event) => ({
  event,
  relatedSnapshot: snapshotById.value.get(event.related_snapshot_id) ?? null,
  previousSnapshot: event.previous_snapshot_id ? (snapshotById.value.get(event.previous_snapshot_id) ?? null) : null,
})));

const cohortCards = computed(() => {
  if (!detail.value) {
    return [];
  }

  return [
    {
      title: "同 provider",
      kicker: detail.value.provider_cohort.label,
      cohort: detail.value.provider_cohort,
    },
    {
      title: "同账号类型",
      kicker: detail.value.account_type_cohort.label,
      cohort: detail.value.account_type_cohort,
    },
    {
      title: "同 provider + 类型",
      kicker: detail.value.provider_account_type_cohort.label,
      cohort: detail.value.provider_account_type_cohort,
    },
  ];
});

const observationNotes = computed(() => {
  if (!detail.value) {
    return [];
  }

  const notes = [
    detail.value.risk_overview.summary,
    ...detail.value.risk_overview.signals.map((signal) => `${signal.label}：${signal.detail}`),
  ];

  const hottestPoint = providerTrendPoints.value.reduce((current, point) => {
    const currentScore = current ? current.is_401_count + current.failed_count : -1;
    const nextScore = point.is_401_count + point.failed_count;
    return nextScore > currentScore ? point : current;
  }, providerTrendPoints.value[0]);

  const totalSnapshots = providerTrendPoints.value.reduce((sum, point) => sum + point.snapshot_count, 0);
  if (hottestPoint && totalSnapshots > 0) {
    notes.push(
      `同组合近 24 小时最热时段出现在 ${formatDateTime(hottestPoint.bucket_start)}，当时 401 ${hottestPoint.is_401_count} 条、失败 ${hottestPoint.failed_count} 条。`,
    );
  }

  return notes;
});

async function loadDetail() {
  if (!Number.isFinite(accountId.value) || accountId.value <= 0) {
    error.value = "无效的账号 ID";
    detail.value = null;
    return;
  }

  loading.value = true;
  error.value = "";

  try {
    detail.value = await getAccountDetail(accountId.value, {
      snapshot_limit: 20,
      event_limit: 20,
    });
  } catch (requestError) {
    detail.value = null;
    error.value = requestError instanceof Error ? requestError.message : "加载账号详情失败";
  } finally {
    loading.value = false;
  }
}

watch(accountId, () => {
  void loadDetail();
}, { immediate: true });

function formatEventType(eventType: string) {
  const labels: Record<string, string> = {
    became_401: "进入 401",
    recovered_from_401: "从 401 恢复",
    quota_exhausted: "额度耗尽",
    disabled_changed: "禁用状态变化",
  };

  return labels[eventType] ?? eventType;
}

function eventTone(eventType: string) {
  if (eventType === "became_401") {
    return "danger" as const;
  }
  if (eventType === "quota_exhausted") {
    return "warning" as const;
  }
  if (eventType === "recovered_from_401") {
    return "success" as const;
  }
  return "muted" as const;
}

function formatBooleanState(value: boolean | null | undefined) {
  if (value === null || value === undefined) {
    return "未记录";
  }
  return value ? "是" : "否";
}

function snapshotTitle(snapshot: AccountSnapshotSummary | null, fallback: string) {
  return snapshot ? formatDateTime(snapshot.checked_at) : fallback;
}

function transitionSummary(event: AccountEventSummary) {
  return `${formatStatusCode(event.from_status_code)} -> ${formatStatusCode(event.to_status_code)}`;
}

function cohortTone(cohort: AccountCohortBreakdown) {
  if (cohort.current_401_accounts > 0 || cohort.became_401_events_last_24h > 0) {
    return "danger" as const;
  }
  return "success" as const;
}

function usageRankLabel(rank: number | null, sampleCount: number) {
  if (rank === null || sampleCount <= 0) {
    return "当前组合没有足够样本";
  }
  return `第 ${rank} / ${sampleCount} 高`;
}

function riskLevelTone(level: string) {
  if (level === "critical" || level === "high") {
    return "danger" as const;
  }
  if (level === "medium") {
    return "warning" as const;
  }
  return "success" as const;
}

function riskLevelLabel(level: string) {
  const labels: Record<string, string> = {
    low: "低风险",
    medium: "中风险",
    high: "高风险",
    critical: "极高风险",
  };

  return labels[level] ?? level;
}

function signalTone(signal: AccountRiskSignal) {
  return signal.tone;
}
</script>

<template>
  <section class="page-section">
    <div class="section-heading">
      <div>
        <p class="section-kicker">账号详情</p>
        <h2 v-if="detail">{{ detail.account.name }}</h2>
        <h2 v-else>账号时间线</h2>
      </div>
      <button class="ghost-button" type="button" @click="loadDetail">刷新</button>
    </div>

    <p v-if="error" class="feedback error">{{ error }}</p>
    <p v-else-if="loading && !detail" class="feedback">正在读取账号详情...</p>

    <template v-if="detail">
      <article class="panel account-summary-panel">
        <div class="account-summary-head">
          <div>
            <p class="section-kicker">当前态</p>
            <h3>{{ detail.account.provider || "未标记 provider" }} / {{ detail.account.account_type || "未标记类型" }}</h3>
          </div>
          <div class="status-stack">
            <StatusPill :tone="detail.account.current_is_401 ? 'danger' : 'success'" :text="formatStatusCode(detail.account.current_status_code)" />
            <StatusPill :tone="detail.account.disabled ? 'muted' : 'success'" :text="detail.account.disabled ? '已禁用' : '活跃'" />
          </div>
        </div>

        <div class="detail-grid">
          <div>
            <p class="subtle-label">auth_index</p>
            <p>{{ detail.account.auth_index }}</p>
          </div>
          <div>
            <p class="subtle-label">邮箱</p>
            <p>{{ detail.account.email || "未记录" }}</p>
          </div>
          <div>
            <p class="subtle-label">最后检测</p>
            <p>{{ formatDateTime(detail.account.current_last_checked_at) }}</p>
          </div>
          <div>
            <p class="subtle-label">当前周额度</p>
            <p>{{ formatPercent(detail.account.current_weekly_used_percent) }}</p>
          </div>
          <div>
            <p class="subtle-label">当前短周期</p>
            <p>{{ formatPercent(detail.account.current_short_used_percent) }}</p>
          </div>
          <div>
            <p class="subtle-label">当前剩余额度</p>
            <p>{{ formatRemaining(detail.account.current_remaining) }}</p>
          </div>
          <div>
            <p class="subtle-label">首次发现</p>
            <p>{{ formatDateTime(detail.account.first_seen_at) }}</p>
          </div>
          <div>
            <p class="subtle-label">最近仍在源</p>
            <p>{{ formatDateTime(detail.account.last_seen_at) }}</p>
          </div>
        </div>
      </article>

      <div class="insight-grid">
        <article
          v-for="card in summaryCards"
          :key="card.label"
          class="event-card insight-card"
          :data-tone="card.tone"
        >
          <p class="section-kicker">{{ card.label }}</p>
          <p class="insight-value">{{ card.value }}</p>
          <p class="subtle-line">{{ card.hint }}</p>
        </article>
      </div>

      <article class="panel">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">归因</p>
            <h3>同组风险对照</h3>
          </div>
        </div>

        <div class="cohort-grid">
          <article
            v-for="item in cohortCards"
            :key="item.title"
            class="event-card cohort-card"
            :data-tone="cohortTone(item.cohort)"
          >
            <div class="event-card-head">
              <div>
                <p class="section-kicker">{{ item.title }}</p>
                <h4 class="cohort-title">{{ item.kicker }}</h4>
              </div>
              <StatusPill :tone="cohortTone(item.cohort)" :text="`${formatPercent(item.cohort.current_401_rate)} 401率`" />
            </div>

            <div class="mini-grid">
              <div>
                <p class="subtle-label">当前样本</p>
                <p class="mini-value">{{ formatCount(item.cohort.total_accounts) }}</p>
              </div>
              <div>
                <p class="subtle-label">24h 已检测</p>
                <p class="mini-value">{{ formatCount(item.cohort.checked_accounts_last_24h) }}</p>
              </div>
              <div>
                <p class="subtle-label">当前 401</p>
                <p class="mini-value">{{ formatCount(item.cohort.current_401_accounts) }}</p>
              </div>
              <div>
                <p class="subtle-label">24h 新增 401</p>
                <p class="mini-value">{{ formatCount(item.cohort.became_401_events_last_24h) }}</p>
              </div>
            </div>
          </article>
        </div>

        <div class="cohort-position-grid">
          <section class="snapshot-brief">
            <p class="section-kicker">周额度位置</p>
            <h4>{{ usageRankLabel(detail.cohort_usage_position.weekly_rank_desc, detail.cohort_usage_position.weekly_compared_accounts) }}</h4>
            <p class="subtle-line">
              当前值 {{ formatPercent(detail.cohort_usage_position.weekly_used_percent) }}，样本 {{ formatCount(detail.cohort_usage_position.weekly_compared_accounts) }} 个。
            </p>
          </section>

          <section class="snapshot-brief">
            <p class="section-kicker">短周期位置</p>
            <h4>{{ usageRankLabel(detail.cohort_usage_position.short_rank_desc, detail.cohort_usage_position.short_compared_accounts) }}</h4>
            <p class="subtle-line">
              当前值 {{ formatPercent(detail.cohort_usage_position.short_used_percent) }}，样本 {{ formatCount(detail.cohort_usage_position.short_compared_accounts) }} 个。
            </p>
          </section>
        </div>
      </article>

      <div class="panel-grid">
        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">风险</p>
              <h3>高风险提示</h3>
            </div>
            <StatusPill :tone="riskLevelTone(detail.risk_overview.level)" :text="riskLevelLabel(detail.risk_overview.level)" />
          </div>

          <p class="risk-headline">{{ detail.risk_overview.headline }}</p>
          <p class="subtle-line">{{ detail.risk_overview.summary }}</p>

          <div class="signal-list">
            <article
              v-for="signal in riskSignals"
              :key="signal.key"
              class="signal-card"
              :data-tone="signalTone(signal)"
            >
              <div class="event-card-head">
                <p class="event-title">{{ signal.label }}</p>
                <StatusPill :tone="signalTone(signal)" :text="signal.label" />
              </div>
              <p class="subtle-line">{{ signal.detail }}</p>
            </article>
          </div>
        </article>

        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">波动</p>
              <h3>同组近 24 小时轨迹</h3>
            </div>
          </div>

          <p class="chart-note">
            口径为同 provider + 类型组合的小时级快照计数，观察 401 与失败快照是否同步抬头。
          </p>
          <CohortRiskTrendChart v-if="providerTrendPoints.length" :points="providerTrendPoints" />
          <p v-else class="feedback">当前组合近 24 小时还没有可用于展示的快照。</p>
        </article>
      </div>

      <div class="panel-grid">
        <article class="panel chart-panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">趋势</p>
              <h3>额度与状态轨迹</h3>
            </div>
          </div>

          <p class="chart-note">
            周额度与短周期共用 0 到 100% 纵轴，红点标记 401。
          </p>
          <AccountUsageChart v-if="chartSnapshots.length" :snapshots="chartSnapshots" />
          <p v-else class="feedback">还没有可用于绘图的快照数据。</p>
        </article>

        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">研究摘要</p>
              <h3>最近窗口观察</h3>
            </div>
          </div>

          <div class="observation-list">
            <p v-for="note in observationNotes" :key="note" class="observation-item">
              {{ note }}
            </p>
          </div>
        </article>
      </div>

      <div class="panel-grid account-detail-grid">
        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">快照</p>
              <h3>最近 20 次检测</h3>
            </div>
          </div>

          <div class="table-wrap">
            <table class="data-table compact">
              <thead>
                <tr>
                  <th>检测时间</th>
                  <th>状态码</th>
                  <th>401</th>
                  <th>周额度</th>
                  <th>短周期</th>
                  <th>剩余</th>
                  <th>快照状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="snapshot in detail.recent_snapshots" :key="snapshot.id">
                  <td>{{ formatDateTime(snapshot.checked_at) }}</td>
                  <td>{{ formatStatusCode(snapshot.probe_status_code) }}</td>
                  <td>{{ snapshot.is_401 ? "是" : "否" }}</td>
                  <td>{{ formatPercent(snapshot.weekly_used_percent) }}</td>
                  <td>{{ formatPercent(snapshot.short_used_percent) }}</td>
                  <td>{{ formatRemaining(snapshot.remaining) }}</td>
                  <td>{{ snapshot.snapshot_status }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">事件</p>
              <h3>最近变更与前后快照</h3>
            </div>
          </div>

          <div v-if="eventTransitions.length" class="transition-list">
            <article v-for="item in eventTransitions" :key="item.event.id" class="event-card transition-card">
              <div class="event-card-head">
                <div>
                  <p class="event-title">{{ formatEventType(item.event.event_type) }}</p>
                  <p class="subtle-line">
                    {{ formatDateTime(item.event.event_time) }} · {{ transitionSummary(item.event) }}
                  </p>
                </div>
                <StatusPill :tone="eventTone(item.event.event_type)" :text="formatEventType(item.event.event_type)" />
              </div>

              <div class="transition-columns">
                <section class="snapshot-brief">
                  <p class="section-kicker">前序快照</p>
                  <h4>{{ snapshotTitle(item.previousSnapshot, "未命中当前窗口") }}</h4>
                  <div v-if="item.previousSnapshot" class="mini-grid">
                    <div>
                      <p class="subtle-label">状态码</p>
                      <p class="mini-value">{{ formatStatusCode(item.previousSnapshot.probe_status_code) }}</p>
                    </div>
                    <div>
                      <p class="subtle-label">401</p>
                      <p class="mini-value">{{ formatBooleanState(item.previousSnapshot.is_401) }}</p>
                    </div>
                    <div>
                      <p class="subtle-label">周额度</p>
                      <p class="mini-value">{{ formatPercent(item.previousSnapshot.weekly_used_percent) }}</p>
                    </div>
                    <div>
                      <p class="subtle-label">短周期</p>
                      <p class="mini-value">{{ formatPercent(item.previousSnapshot.short_used_percent) }}</p>
                    </div>
                  </div>
                  <p v-else class="snapshot-empty">前序快照不在当前详情窗口内，无法直接展示更多上下文。</p>
                </section>

                <section class="snapshot-brief">
                  <p class="section-kicker">触发快照</p>
                  <h4>{{ snapshotTitle(item.relatedSnapshot, "未加载到触发快照") }}</h4>
                  <div v-if="item.relatedSnapshot" class="mini-grid">
                    <div>
                      <p class="subtle-label">状态码</p>
                      <p class="mini-value">{{ formatStatusCode(item.relatedSnapshot.probe_status_code) }}</p>
                    </div>
                    <div>
                      <p class="subtle-label">401</p>
                      <p class="mini-value">{{ formatBooleanState(item.relatedSnapshot.is_401) }}</p>
                    </div>
                    <div>
                      <p class="subtle-label">周额度</p>
                      <p class="mini-value">{{ formatPercent(item.relatedSnapshot.weekly_used_percent) }}</p>
                    </div>
                    <div>
                      <p class="subtle-label">短周期</p>
                      <p class="mini-value">{{ formatPercent(item.relatedSnapshot.short_used_percent) }}</p>
                    </div>
                  </div>
                  <p v-else class="snapshot-empty">当前窗口内没有加载到事件关联快照。</p>
                </section>
              </div>
            </article>
          </div>
          <p v-else class="feedback">最近窗口内还没有状态变更事件。</p>
        </article>
      </div>
    </template>
  </section>
</template>
