<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { getDashboardOverview } from "@/api/client";
import MetricCard from "@/components/MetricCard.vue";
import TrendChart from "@/components/TrendChart.vue";
import { formatCount, formatDateTime, formatDurationMs, formatPercent } from "@/lib/format";
import type { DashboardOverviewResponse, DimensionBreakdownItem } from "@/types/api";


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

function cohortSummary(item: DimensionBreakdownItem) {
  return `${formatCount(item.active_accounts)} 活跃 / ${formatCount(item.disabled_accounts)} 禁用`;
}

function latestScanJobErrorSummary() {
  const latestScanJob = overview.value?.latest_scan_job;
  if (!latestScanJob) {
    return "无";
  }
  if (latestScanJob.error_message?.trim()) {
    return latestScanJob.error_message;
  }
  if (latestScanJob.status === "failed" || latestScanJob.status === "partial_failed") {
    return "未记录错误详情";
  }
  return "无";
}
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
        <MetricCard label="活跃账号" :value="formatCount(overview.active_accounts)" accent="teal" />
        <MetricCard label="已禁用" :value="formatCount(overview.disabled_accounts)" />
        <MetricCard label="已删除源账号" :value="formatCount(overview.deleted_accounts)" />
        <MetricCard
          label="24h 新增 401"
          :value="formatCount(overview.new_401_events_last_24h)"
          hint="事件表口径"
          accent="sun"
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
            <RouterLink class="inline-link" to="/scan-jobs">查看全部</RouterLink>
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
            <div class="detail-row">
              <span>任务级错误</span>
              <strong>{{ latestScanJobErrorSummary() }}</strong>
            </div>
          </div>
          <p v-else class="feedback">还没有扫描任务数据。</p>
        </article>
      </div>

      <div class="panel-grid">
        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">Provider 研究</p>
              <h3>按 provider 聚合的风险分布</h3>
            </div>
          </div>

          <div v-if="overview.provider_breakdown.length" class="table-wrap">
            <table class="data-table compact">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>当前账号</th>
                  <th>当前 401</th>
                  <th>24h 新增 401</th>
                  <th>401 率</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in overview.provider_breakdown" :key="item.label">
                  <td>
                    <strong>{{ item.label }}</strong>
                    <p class="subtle-line">{{ cohortSummary(item) }}</p>
                  </td>
                  <td>{{ formatCount(item.total_accounts) }}</td>
                  <td>{{ formatCount(item.current_401_accounts) }}</td>
                  <td>{{ formatCount(item.became_401_events_last_24h) }}</td>
                  <td>{{ formatPercent(item.current_401_rate) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="feedback">还没有可用于 provider 聚合的账号样本。</p>
        </article>

        <article class="panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">类型研究</p>
              <h3>按账号类型聚合的风险分布</h3>
            </div>
          </div>

          <div v-if="overview.account_type_breakdown.length" class="table-wrap">
            <table class="data-table compact">
              <thead>
                <tr>
                  <th>类型</th>
                  <th>当前账号</th>
                  <th>当前 401</th>
                  <th>24h 新增 401</th>
                  <th>401 率</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in overview.account_type_breakdown" :key="item.label">
                  <td>
                    <strong>{{ item.label }}</strong>
                    <p class="subtle-line">{{ cohortSummary(item) }}</p>
                  </td>
                  <td>{{ formatCount(item.total_accounts) }}</td>
                  <td>{{ formatCount(item.current_401_accounts) }}</td>
                  <td>{{ formatCount(item.became_401_events_last_24h) }}</td>
                  <td>{{ formatPercent(item.current_401_rate) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="feedback">还没有可用于账号类型聚合的样本。</p>
        </article>
      </div>
    </template>
  </section>
</template>
