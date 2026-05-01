<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { getAccountDetail } from "@/api/client";
import StatusPill from "@/components/StatusPill.vue";
import { formatDateTime, formatPercent, formatStatusCode } from "@/lib/format";
import type { AccountDetailResponse } from "@/types/api";


const route = useRoute();
const loading = ref(false);
const error = ref("");
const detail = ref<AccountDetailResponse | null>(null);

const accountId = computed(() => Number(route.params.accountId));

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
        </div>
      </article>

      <div class="panel-grid">
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
                  <th>额度</th>
                  <th>快照状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="snapshot in detail.recent_snapshots" :key="snapshot.id">
                  <td>{{ formatDateTime(snapshot.checked_at) }}</td>
                  <td>{{ formatStatusCode(snapshot.probe_status_code) }}</td>
                  <td>{{ snapshot.is_401 ? "是" : "否" }}</td>
                  <td>周 {{ formatPercent(snapshot.weekly_used_percent) }}</td>
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
              <h3>最近 20 条变更</h3>
            </div>
          </div>

          <div class="timeline-list">
            <div v-for="event in detail.recent_events" :key="event.id" class="timeline-item">
              <div class="timeline-dot" />
              <div>
                <p class="timeline-title">{{ event.event_type }}</p>
                <p class="subtle-line">
                  {{ formatDateTime(event.event_time) }} · {{ event.from_status_code ?? "?" }} -> {{ event.to_status_code ?? "?" }}
                </p>
              </div>
            </div>
          </div>
        </article>
      </div>
    </template>
  </section>
</template>
