<script setup lang="ts">
import { onMounted, ref } from "vue";

import { getDashboardOverview } from "@/api/client";
import MetricCard from "@/components/MetricCard.vue";
import TrendChart from "@/components/TrendChart.vue";
import { formatCount, formatDateTime, formatDurationMs } from "@/lib/format";
import type { DashboardOverviewResponse } from "@/types/api";


const loading = ref(false);
const error = ref("");
const overview = ref<DashboardOverviewResponse | null>(null);

async function loadOverview() {
  loading.value = true;
  error.value = "";

  try {
    overview.value = await getDashboardOverview();
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "加载概览失败";
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void loadOverview();
});
</script>

<template>
  <section class="page-section">
    <div class="section-heading">
      <div>
        <p class="section-kicker">全局态势</p>
        <h2>24 小时内的风险轮廓</h2>
      </div>
      <button class="ghost-button" type="button" @click="loadOverview">刷新</button>
    </div>

    <p v-if="error" class="feedback error">{{ error }}</p>
    <p v-else-if="loading && !overview" class="feedback">正在读取仪表盘数据...</p>

    <template v-if="overview">
      <div class="metric-grid">
        <MetricCard label="总账号数" :value="formatCount(overview.total_accounts)" accent="ink" />
        <MetricCard label="当前 401" :value="formatCount(overview.current_401_accounts)" accent="sun" />
        <MetricCard
          label="额度异常"
          :value="formatCount(overview.current_invalid_quota_accounts)"
          accent="rose"
        />
        <MetricCard label="活跃账号" :value="formatCount(overview.active_accounts)" accent="teal" />
        <MetricCard label="已禁用" :value="formatCount(overview.disabled_accounts)" />
        <MetricCard label="已删除源账号" :value="formatCount(overview.deleted_accounts)" />
        <MetricCard
          label="24h 新增 401"
          :value="formatCount(overview.new_401_events_last_24h)"
          hint="事件表口径"
          accent="sun"
        />
        <MetricCard
          label="24h 新增额度异常"
          :value="formatCount(overview.new_quota_events_last_24h)"
          hint="事件表口径"
          accent="rose"
        />
      </div>

      <div class="panel-grid">
        <article class="panel chart-panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">趋势</p>
              <h3>最近 24 小时新增 401</h3>
            </div>
          </div>
          <TrendChart :points="overview.recent_401_trend" />
        </article>

        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">最近扫描</p>
              <h3>最新任务摘要</h3>
            </div>
          </div>

          <div v-if="overview.latest_scan_job" class="detail-list">
            <div class="detail-row">
              <span>触发方式</span>
              <strong>{{ overview.latest_scan_job.trigger_mode }}</strong>
            </div>
            <div class="detail-row">
              <span>任务状态</span>
              <strong>{{ overview.latest_scan_job.status }}</strong>
            </div>
            <div class="detail-row">
              <span>扫描开始</span>
              <strong>{{ formatDateTime(overview.latest_scan_job.scan_started_at) }}</strong>
            </div>
            <div class="detail-row">
              <span>扫描结束</span>
              <strong>{{ formatDateTime(overview.latest_scan_job.scan_finished_at) }}</strong>
            </div>
            <div class="detail-row">
              <span>耗时</span>
              <strong>{{ formatDurationMs(overview.latest_scan_job.duration_ms) }}</strong>
            </div>
            <div class="detail-row">
              <span>成功 / 失败</span>
              <strong>
                {{ overview.latest_scan_job.success_accounts }} / {{ overview.latest_scan_job.failed_accounts }}
              </strong>
            </div>
          </div>
          <p v-else class="feedback">还没有扫描任务数据。</p>
        </article>
      </div>
    </template>
  </section>
</template>
