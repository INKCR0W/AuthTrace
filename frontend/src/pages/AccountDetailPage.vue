<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { getAccountDetail } from "@/api/client";
import AccountUsageChart from "@/components/AccountUsageChart.vue";
import StatusPill from "@/components/StatusPill.vue";
import { formatDateTime, formatPercent, formatRemaining, formatStatusCode } from "@/lib/format";
import type { AccountDetailResponse, AccountEventSummary, AccountSnapshotSummary } from "@/types/api";


const route = useRoute();
const loading = ref(false);
const error = ref("");
const detail = ref<AccountDetailResponse | null>(null);

const accountId = computed(() => Number(route.params.accountId));
const recentSnapshots = computed(() => detail.value?.recent_snapshots ?? []);
const chartSnapshots = computed(() => [...recentSnapshots.value].reverse());
const snapshotById = computed(() => new Map(recentSnapshots.value.map((snapshot) => [snapshot.id, snapshot])));

const summaryCards = computed(() => {
  const snapshots = recentSnapshots.value;
  const weeklyHot = snapshots.filter((snapshot) => toNumber(snapshot.weekly_used_percent) >= 80);
  const shortHot = snapshots.filter((snapshot) => toNumber(snapshot.short_used_percent) >= 80);
  const stressed = snapshots.filter((snapshot) => snapshot.invalid_quota || snapshot.limit_reached || snapshot.allowed === false);
  const failed = snapshots.filter((snapshot) => snapshot.snapshot_status !== "success");
  const exceptionCount = new Set([
    ...stressed.map((snapshot) => snapshot.id),
    ...failed.map((snapshot) => snapshot.id),
  ]).size;

  return [
    {
      label: "样本窗口",
      value: `${snapshots.length} 次`,
      hint: "当前详情接口返回的最近快照数",
      tone: "muted" as const,
    },
    {
      label: "周额度高压",
      value: `${weeklyHot.length} 次`,
      hint: weeklyHot[0] ? `最近一次 ${formatDateTime(weeklyHot[0].checked_at)}` : "窗口内未出现周额度 >= 80%",
      tone: weeklyHot.length > 0 ? "warning" as const : "success" as const,
    },
    {
      label: "短周期高压",
      value: `${shortHot.length} 次`,
      hint: shortHot[0] ? `最近一次 ${formatDateTime(shortHot[0].checked_at)}` : "窗口内未出现短周期 >= 80%",
      tone: shortHot.length > 0 ? "warning" as const : "success" as const,
    },
    {
      label: "异常或失败",
      value: `${exceptionCount} 次`,
      hint: stressed[0]
        ? `最近一次异常 ${formatDateTime(stressed[0].checked_at)}`
        : failed[0]
          ? `最近一次失败 ${formatDateTime(failed[0].checked_at)}`
          : "窗口内未发现异常或失败快照",
      tone: exceptionCount > 0 ? "danger" as const : "success" as const,
    },
  ];
});

const eventTransitions = computed(() => (detail.value?.recent_events ?? []).map((event) => ({
  event,
  relatedSnapshot: snapshotById.value.get(event.related_snapshot_id) ?? null,
  previousSnapshot: event.previous_snapshot_id ? (snapshotById.value.get(event.previous_snapshot_id) ?? null) : null,
})));

const observationNotes = computed(() => {
  const notes: string[] = [];
  const latestBecame401 = eventTransitions.value.find((item) => item.event.event_type === "became_401");
  const failedSnapshots = recentSnapshots.value.filter((snapshot) => snapshot.snapshot_status !== "success");
  const highWeekly = recentSnapshots.value.filter((snapshot) => toNumber(snapshot.weekly_used_percent) >= 80).length;
  const highShort = recentSnapshots.value.filter((snapshot) => toNumber(snapshot.short_used_percent) >= 80).length;

  if (latestBecame401?.previousSnapshot && latestBecame401.relatedSnapshot) {
    notes.push(
      [
        `最近一次 401 事件发生在 ${formatDateTime(latestBecame401.event.event_time)}`,
        `前序快照周额度 ${formatPercent(latestBecame401.previousSnapshot.weekly_used_percent)}`,
        `短周期 ${formatPercent(latestBecame401.previousSnapshot.short_used_percent)}`,
        `当前快照状态码 ${formatStatusCode(latestBecame401.relatedSnapshot.probe_status_code)}`,
      ].join("，"),
    );
  } else if (latestBecame401) {
    notes.push("最近一次 401 事件在当前快照窗口内缺少完整前序快照，暂时只能确认发生时间，无法直接比较前后额度。");
  }

  if (highWeekly > 0 || highShort > 0) {
    notes.push(`最近样本窗口内出现周额度高压 ${highWeekly} 次，短周期高压 ${highShort} 次。`);
  }

  if (failedSnapshots.length > 0) {
    notes.push(`当前窗口内有 ${failedSnapshots.length} 条非 success 快照，联调时需要同时关注管理端可用性与解析失败路径。`);
  }

  if (notes.length === 0) {
    notes.push("最近样本窗口内未发现 401、额度异常或失败快照，当前账号状态相对平稳。");
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

function toNumber(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return -1;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : -1;
}

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
            <StatusPill :tone="detail.account.current_invalid_quota ? 'warning' : 'muted'" :text="detail.account.current_invalid_quota ? '额度异常' : '额度正常'" />
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

      <div class="panel-grid">
        <article class="panel chart-panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">趋势</p>
              <h3>额度与状态轨迹</h3>
            </div>
          </div>

          <p class="chart-note">
            周额度与短周期共用 0 到 100% 纵轴，红点标记 401，灰色三角标记额度异常。
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
