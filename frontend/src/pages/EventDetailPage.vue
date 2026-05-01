<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import { getEventDetail } from "@/api/client";
import JsonPayloadViewer from "@/components/JsonPayloadViewer.vue";
import StatusPill from "@/components/StatusPill.vue";
import { formatDateTime, formatPercent, formatRemaining, formatStatusCode } from "@/lib/format";
import type { AccountEventSummary, AccountSnapshotSummary, EventDetailResponse } from "@/types/api";


const route = useRoute();
const loading = ref(false);
const error = ref("");
const detail = ref<EventDetailResponse | null>(null);

const eventId = computed(() => Number(route.params.eventId));
const item = computed(() => detail.value?.item ?? null);
const account = computed(() => item.value?.account ?? null);
const event = computed(() => item.value?.event ?? null);
const relatedSnapshot = computed(() => item.value?.related_snapshot ?? null);
const previousSnapshot = computed(() => item.value?.previous_snapshot ?? null);
const contextSnapshots = computed(() => detail.value?.context_snapshots ?? []);
const contextEvents = computed(() => detail.value?.context_events ?? []);

const summaryCards = computed(() => {
  const snapshots = contextSnapshots.value;
  const failedCount = snapshots.filter((snapshot) => snapshot.snapshot_status !== "success").length;
  const currentCount = snapshots.length > 0 ? 1 : 0;

  return [
    {
      label: "事件窗口样本",
      value: `${snapshots.length} 次`,
      hint: "仅包含事件发生时点及此前的上下文快照",
      tone: "muted" as const,
    },
    {
      label: "触发快照",
      value: `${currentCount} 次`,
      hint: relatedSnapshot.value ? formatDateTime(relatedSnapshot.value.checked_at) : "未加载到触发快照",
      tone: event.value?.to_is_401 ? "danger" as const : "success" as const,
    },
    {
      label: "失败样本",
      value: `${failedCount} 次`,
      hint: failedCount > 0 ? "窗口内存在非 success 快照" : "窗口内没有失败快照",
      tone: failedCount > 0 ? "warning" as const : "success" as const,
    },
  ];
});

async function loadDetail() {
  if (!Number.isFinite(eventId.value) || eventId.value <= 0) {
    detail.value = null;
    error.value = "无效的事件 ID";
    return;
  }

  loading.value = true;
  error.value = "";

  try {
    detail.value = await getEventDetail(eventId.value, {
      snapshot_limit: 8,
      event_limit: 8,
    });
  } catch (requestError) {
    detail.value = null;
    error.value = requestError instanceof Error ? requestError.message : "加载事件详情失败";
  } finally {
    loading.value = false;
  }
}

watch(eventId, () => {
  void loadDetail();
}, { immediate: true });

function formatEventType(eventType: string) {
  const labels: Record<string, string> = {
    became_401: "进入 401",
    recovered_from_401: "从 401 恢复",
    disabled_changed: "禁用状态变化",
    quota_exhausted: "额度耗尽",
  };

  return labels[eventType] ?? eventType;
}

function eventTone(eventType: string) {
  if (eventType === "became_401") {
    return "danger" as const;
  }
  if (eventType === "recovered_from_401") {
    return "success" as const;
  }
  if (eventType === "quota_exhausted") {
    return "warning" as const;
  }
  return "muted" as const;
}

function formatBooleanState(value: boolean | null | undefined) {
  if (value === null || value === undefined) {
    return "未记录";
  }
  return value ? "是" : "否";
}

function transitionSummary(itemEvent: AccountEventSummary) {
  return `${formatStatusCode(itemEvent.from_status_code)} -> ${formatStatusCode(itemEvent.to_status_code)}`;
}

function snapshotMarker(snapshot: AccountSnapshotSummary) {
  if (snapshot.id === relatedSnapshot.value?.id) {
    return "触发快照";
  }
  if (snapshot.id === previousSnapshot.value?.id) {
    return "前序快照";
  }
  return "上下文";
}
</script>

<template>
  <section class="page-section">
    <div class="section-heading">
      <div>
        <p class="section-kicker">事件详情</p>
        <h2 v-if="event">{{ formatEventType(event.event_type) }}</h2>
        <h2 v-else>事件研究视图</h2>
      </div>
      <button class="ghost-button" type="button" @click="loadDetail">刷新</button>
    </div>

    <p v-if="error" class="feedback error">{{ error }}</p>
    <p v-else-if="loading && !detail" class="feedback">正在读取事件详情...</p>

    <template v-if="detail && account && event && relatedSnapshot">
      <article class="panel account-summary-panel">
        <div class="account-summary-head">
          <div>
            <p class="section-kicker">事件主体</p>
            <h3>{{ account.name }}</h3>
          </div>
          <div class="status-stack">
            <StatusPill :tone="eventTone(event.event_type)" :text="formatEventType(event.event_type)" />
            <StatusPill :tone="event.to_is_401 ? 'danger' : 'success'" :text="formatDateTime(event.event_time)" />
          </div>
        </div>

        <div class="detail-grid">
          <div>
            <p class="subtle-label">账号维度</p>
            <p>{{ account.provider || "未标记 provider" }} / {{ account.account_type || "未标记类型" }}</p>
          </div>
          <div>
            <p class="subtle-label">状态转移</p>
            <p>{{ transitionSummary(event) }}</p>
          </div>
          <div>
            <p class="subtle-label">关联扫描任务</p>
            <p>#{{ relatedSnapshot.scan_job_id }}</p>
          </div>
          <div>
            <p class="subtle-label">当前账号状态</p>
            <p>{{ account.current_is_401 ? "当前仍为 401" : "当前已恢复或正常" }}</p>
          </div>
        </div>

        <div class="nav-tabs">
          <RouterLink class="nav-tab" to="/events">返回事件列表</RouterLink>
          <RouterLink class="nav-tab" :to="`/accounts/${account.id}`">查看账号详情</RouterLink>
          <RouterLink class="nav-tab" to="/scan-jobs">查看扫描任务页</RouterLink>
        </div>
      </article>

      <div class="insight-grid event-detail-cards">
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
        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">对照</p>
              <h3>触发前后快照</h3>
            </div>
          </div>

          <div class="transition-columns">
            <section class="snapshot-brief">
              <p class="section-kicker">前序快照</p>
              <h4>{{ previousSnapshot ? formatDateTime(previousSnapshot.checked_at) : "未记录" }}</h4>
              <div v-if="previousSnapshot" class="mini-grid">
                <div>
                  <p class="subtle-label">状态码</p>
                  <p class="mini-value">{{ formatStatusCode(previousSnapshot.probe_status_code) }}</p>
                </div>
                <div>
                  <p class="subtle-label">401</p>
                  <p class="mini-value">{{ formatBooleanState(previousSnapshot.is_401) }}</p>
                </div>
                <div>
                  <p class="subtle-label">周额度</p>
                  <p class="mini-value">{{ formatPercent(previousSnapshot.weekly_used_percent) }}</p>
                </div>
                <div>
                  <p class="subtle-label">剩余</p>
                  <p class="mini-value">{{ formatRemaining(previousSnapshot.remaining) }}</p>
                </div>
              </div>
              <p v-else class="snapshot-empty">本次事件没有上一条快照可用于对照。</p>
              <div v-if="previousSnapshot" class="json-viewer-stack">
                <JsonPayloadViewer title="auth-file 原始 JSON" :payload="previousSnapshot.raw_auth_file_json" />
                <JsonPayloadViewer title="usage 原始 JSON" :payload="previousSnapshot.raw_usage_json" />
              </div>
            </section>

            <section class="snapshot-brief">
              <p class="section-kicker">触发快照</p>
              <h4>{{ formatDateTime(relatedSnapshot.checked_at) }}</h4>
              <div class="mini-grid">
                <div>
                  <p class="subtle-label">状态码</p>
                  <p class="mini-value">{{ formatStatusCode(relatedSnapshot.probe_status_code) }}</p>
                </div>
                <div>
                  <p class="subtle-label">401</p>
                  <p class="mini-value">{{ formatBooleanState(relatedSnapshot.is_401) }}</p>
                </div>
                <div>
                  <p class="subtle-label">周额度</p>
                  <p class="mini-value">{{ formatPercent(relatedSnapshot.weekly_used_percent) }}</p>
                </div>
                <div>
                  <p class="subtle-label">剩余</p>
                  <p class="mini-value">{{ formatRemaining(relatedSnapshot.remaining) }}</p>
                </div>
              </div>
              <p class="table-inline-note">{{ relatedSnapshot.error_message || relatedSnapshot.status_message || "无额外提示" }}</p>
              <div class="json-viewer-stack">
                <JsonPayloadViewer title="auth-file 原始 JSON" :payload="relatedSnapshot.raw_auth_file_json" />
                <JsonPayloadViewer title="usage 原始 JSON" :payload="relatedSnapshot.raw_usage_json" />
              </div>
            </section>
          </div>
        </article>

        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">结论</p>
              <h3>事件研究摘要</h3>
            </div>
          </div>

          <div class="observation-list">
            <p class="observation-item">
              事件发生于 {{ formatDateTime(event.event_time) }}，账号 {{ account.name }} 从
              {{ formatStatusCode(event.from_status_code) }} 变为 {{ formatStatusCode(event.to_status_code) }}。
            </p>
            <p class="observation-item">
              当前详情窗口共回放 {{ contextSnapshots.length }} 条上下文快照，可直接核对事件触发前后的原始 `auth-file` 与 `usage` 返回。
            </p>
            <p class="observation-item">
              当前账号{{ account.current_is_401 ? "仍处于 401 状态" : "已脱离 401 状态" }}；如需继续看更长时间线，可跳转账号详情页。
            </p>
          </div>
        </article>
      </div>

      <div class="panel-grid event-context-grid">
        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">样本</p>
              <h3>事件上下文快照</h3>
            </div>
          </div>

          <div class="table-wrap">
            <table class="data-table compact">
              <thead>
                <tr>
                  <th>标记</th>
                  <th>检测时间</th>
                  <th>状态码</th>
                  <th>401</th>
                  <th>周额度</th>
                  <th>剩余</th>
                  <th>快照状态</th>
                  <th>联调上下文</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="snapshot in contextSnapshots" :key="snapshot.id">
                  <td>
                    <StatusPill
                      :tone="snapshot.id === relatedSnapshot.id ? 'danger' : snapshot.id === previousSnapshot?.id ? 'warning' : 'muted'"
                      :text="snapshotMarker(snapshot)"
                    />
                  </td>
                  <td>{{ formatDateTime(snapshot.checked_at) }}</td>
                  <td>{{ formatStatusCode(snapshot.probe_status_code) }}</td>
                  <td>{{ snapshot.is_401 ? "是" : "否" }}</td>
                  <td>{{ formatPercent(snapshot.weekly_used_percent) }}</td>
                  <td>{{ formatRemaining(snapshot.remaining) }}</td>
                  <td>{{ snapshot.snapshot_status }}</td>
                  <td>
                    <p class="table-inline-note">{{ snapshot.error_message || snapshot.status_message || "无额外提示" }}</p>
                    <div class="json-viewer-stack">
                      <JsonPayloadViewer title="auth-file 原始 JSON" :payload="snapshot.raw_auth_file_json" />
                      <JsonPayloadViewer title="usage 原始 JSON" :payload="snapshot.raw_usage_json" />
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
              <p class="section-kicker">关联事件</p>
              <h3>该账号此前事件</h3>
            </div>
          </div>

          <div v-if="contextEvents.length" class="transition-list">
            <article v-for="contextEvent in contextEvents" :key="contextEvent.id" class="event-card transition-card">
              <div class="event-card-head">
                <div>
                  <p class="event-title">{{ formatEventType(contextEvent.event_type) }}</p>
                  <p class="subtle-line">
                    {{ formatDateTime(contextEvent.event_time) }} · {{ transitionSummary(contextEvent) }}
                  </p>
                </div>
                <StatusPill :tone="eventTone(contextEvent.event_type)" :text="formatEventType(contextEvent.event_type)" />
              </div>
              <p class="subtle-line">
                related_snapshot_id = {{ contextEvent.related_snapshot_id }}，
                previous_snapshot_id = {{ contextEvent.previous_snapshot_id ?? "无" }}
              </p>
            </article>
          </div>
          <p v-else class="feedback">当前账号在该事件之前没有更多状态变更事件。</p>
        </article>
      </div>
    </template>
  </section>
</template>
