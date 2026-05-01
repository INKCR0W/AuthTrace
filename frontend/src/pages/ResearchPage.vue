<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { getResearchOverview } from "@/api/client";
import DistributionBarChart from "@/components/DistributionBarChart.vue";
import MetricCard from "@/components/MetricCard.vue";
import { formatCount, formatDateTime, formatPercent } from "@/lib/format";
import type { ResearchBucketCount, ResearchOverviewResponse } from "@/types/api";


const loading = ref(false);
const error = ref("");
const windowDays = ref(7);
const overview = ref<ResearchOverviewResponse | null>(null);

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

async function loadOverview() {
  loading.value = true;
  error.value = "";

  try {
    overview.value = await getResearchOverview({ window_days: windowDays.value });
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "加载研究数据失败";
  } finally {
    loading.value = false;
  }
}

function bucketSummary(item: ResearchBucketCount) {
  return `${item.label}：${formatCount(item.count)} 次`;
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
          <span class="subtle-label">窗口</span>
          <select v-model="windowDays" class="input-field compact-select" @change="loadOverview">
            <option :value="7">最近 7 天</option>
            <option :value="14">最近 14 天</option>
            <option :value="30">最近 30 天</option>
          </select>
        </label>
        <button class="ghost-button" type="button" @click="loadOverview">刷新</button>
      </div>
    </div>

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
      </div>

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

          <div v-if="overview.pre_401_insights.top_status_messages.length" class="observation-list">
            <p class="subtle-label">高频 status_message</p>
            <p
              v-for="item in overview.pre_401_insights.top_status_messages"
              :key="item.key"
              class="observation-item"
            >
              {{ item.label }} · {{ formatCount(item.count) }} 次
            </p>
          </div>
          <p v-else class="feedback">当前窗口内，前序正常样本没有留下稳定的 `status_message`。</p>
        </article>
      </div>

      <div class="panel-grid research-band-grid">
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
        <p v-else class="feedback">当前窗口内还没有可供研究的组合样本。</p>
      </article>
    </template>
  </section>
</template>
