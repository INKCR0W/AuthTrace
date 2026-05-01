<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import { getScanJobDetail, getScanJobs } from "@/api/client";
import StatusPill from "@/components/StatusPill.vue";
import { formatCount, formatDateTime, formatDurationMs, formatPercent } from "@/lib/format";
import type { ScanJobDetailResponse, ScanJobListResponse, ScanJobSnapshotSample } from "@/types/api";


const pageSize = 20;
const loading = ref(false);
const error = ref("");
const result = ref<ScanJobListResponse | null>(null);
const offset = ref(0);
const selectedJobId = ref<number | null>(null);
const detailLoading = ref(false);
const detailError = ref("");
const detailResult = ref<ScanJobDetailResponse | null>(null);
let detailRequestToken = 0;

const filters = reactive({
  status: "",
  trigger_mode: "",
});

async function loadScanJobs() {
  loading.value = true;
  error.value = "";

  try {
    result.value = await getScanJobs({
      status: filters.status || undefined,
      trigger_mode: filters.trigger_mode || undefined,
      limit: pageSize,
      offset: offset.value,
    });
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "加载扫描任务失败";
  } finally {
    loading.value = false;
  }
}

function clearDetailSelection() {
  detailRequestToken += 1;
  selectedJobId.value = null;
  detailLoading.value = false;
  detailResult.value = null;
  detailError.value = "";
}

function resetFilters() {
  filters.status = "";
  filters.trigger_mode = "";
  offset.value = 0;
  clearDetailSelection();
  void loadScanJobs();
}

function previousPage() {
  offset.value = Math.max(0, offset.value - pageSize);
  clearDetailSelection();
  void loadScanJobs();
}

function nextPage() {
  if (!result.value || offset.value + pageSize >= result.value.total) {
    return;
  }
  offset.value += pageSize;
  clearDetailSelection();
  void loadScanJobs();
}

async function toggleDetail(scanJobId: number) {
  if (selectedJobId.value === scanJobId) {
    clearDetailSelection();
    return;
  }

  detailRequestToken += 1;
  const requestToken = detailRequestToken;
  selectedJobId.value = scanJobId;
  detailLoading.value = true;
  detailError.value = "";
  detailResult.value = null;

  try {
    const response = await getScanJobDetail(scanJobId);
    if (requestToken !== detailRequestToken || selectedJobId.value !== scanJobId) {
      return;
    }
    detailResult.value = response;
  } catch (requestError) {
    if (requestToken !== detailRequestToken || selectedJobId.value !== scanJobId) {
      return;
    }
    detailError.value = requestError instanceof Error ? requestError.message : "加载任务详情失败";
  } finally {
    if (requestToken === detailRequestToken && selectedJobId.value === scanJobId) {
      detailLoading.value = false;
    }
  }
}

function scanJobTone(status: string) {
  if (status === "success") {
    return "success";
  }
  if (status === "running") {
    return "warning";
  }
  return "danger";
}

function sampleTone(sample: ScanJobSnapshotSample) {
  if (sample.is_401) {
    return "danger";
  }
  if (sample.invalid_quota || sample.snapshot_status !== "success") {
    return "warning";
  }
  return "muted";
}

function quotaSummary(sample: ScanJobSnapshotSample) {
  const weekly = sample.weekly_used_percent ? `周额度 ${formatPercent(Number(sample.weekly_used_percent))}` : "周额度无记录";
  const short = sample.short_used_percent ? `短周期 ${formatPercent(Number(sample.short_used_percent))}` : "短周期无记录";
  const remaining = sample.remaining ? `剩余 ${sample.remaining}` : "剩余额度无记录";
  return `${weekly} / ${short} / ${remaining}`;
}

onMounted(() => {
  void loadScanJobs();
});
</script>

<template>
  <section class="page-section">
    <div class="section-heading">
      <div>
        <p class="section-kicker">扫描任务</p>
        <h2>最近几轮执行轨迹</h2>
      </div>
    </div>

    <form class="filter-bar scan-job-filter-bar" @submit.prevent="offset = 0; clearDetailSelection(); loadScanJobs()">
      <select v-model="filters.status" class="input-field">
        <option value="">任务状态</option>
        <option value="running">running</option>
        <option value="success">success</option>
        <option value="partial_failed">partial_failed</option>
        <option value="failed">failed</option>
      </select>
      <select v-model="filters.trigger_mode" class="input-field">
        <option value="">触发方式</option>
        <option value="manual">manual</option>
        <option value="scheduler">scheduler</option>
        <option value="retry">retry</option>
      </select>
      <div class="filter-actions">
        <button class="primary-button" type="submit">查询</button>
        <button class="ghost-button" type="button" @click="resetFilters">重置</button>
      </div>
    </form>

    <p v-if="error" class="feedback error">{{ error }}</p>
    <p v-else-if="loading && !result" class="feedback">正在读取扫描任务...</p>

    <template v-if="result">
      <div class="table-meta">
        <span>共 {{ formatCount(result.total) }} 条</span>
        <span>当前偏移 {{ formatCount(result.offset) }}</span>
      </div>

      <div class="event-stack">
        <article v-for="item in result.items" :key="item.id" class="event-card">
          <div class="event-card-head">
            <div>
              <p class="event-type">任务 #{{ item.id }}</p>
              <p class="subtle-line">开始于 {{ formatDateTime(item.scan_started_at) }}</p>
            </div>
            <div class="status-stack">
              <StatusPill :tone="scanJobTone(item.status)" :text="item.status" />
              <StatusPill tone="muted" :text="item.trigger_mode" />
              <button class="ghost-button compact-button" type="button" @click="toggleDetail(item.id)">
                {{ selectedJobId === item.id ? "收起详情" : "查看详情" }}
              </button>
            </div>
          </div>

          <div class="detail-grid">
            <div>
              <p class="subtle-label">覆盖范围</p>
              <p>总账号 {{ formatCount(item.total_accounts) }}，可扫描 {{ formatCount(item.eligible_accounts) }}</p>
              <p class="subtle-line">已执行 {{ formatCount(item.scanned_accounts) }}</p>
            </div>
            <div>
              <p class="subtle-label">结果产出</p>
              <p>成功 {{ formatCount(item.success_accounts) }} / 失败 {{ formatCount(item.failed_accounts) }}</p>
              <p class="subtle-line">
                新增 401 {{ formatCount(item.new_401_events) }}，新增额度异常 {{ formatCount(item.new_quota_events) }}
              </p>
            </div>
            <div>
              <p class="subtle-label">时间信息</p>
              <p>结束于 {{ formatDateTime(item.scan_finished_at) }}</p>
              <p class="subtle-line">耗时 {{ formatDurationMs(item.duration_ms) }}</p>
            </div>
            <div>
              <p class="subtle-label">失败摘要</p>
              <p>{{ item.error_message || "无任务级错误" }}</p>
            </div>
          </div>

          <div v-if="selectedJobId === item.id" class="scan-job-detail-block">
            <p v-if="detailError" class="feedback error">{{ detailError }}</p>
            <p v-else-if="detailLoading" class="feedback">正在加载任务详情...</p>

            <template v-else-if="detailResult">
              <div class="detail-grid">
                <div>
                  <p class="subtle-label">快照分布</p>
                  <p>共 {{ formatCount(detailResult.snapshot_stats.total_snapshots) }} 条快照</p>
                  <p class="subtle-line">
                    success {{ formatCount(detailResult.snapshot_stats.success_snapshots) }} /
                    partial_failed {{ formatCount(detailResult.snapshot_stats.partial_failed_snapshots) }} /
                    failed {{ formatCount(detailResult.snapshot_stats.failed_snapshots) }}
                  </p>
                </div>
                <div>
                  <p class="subtle-label">风险覆盖</p>
                  <p>401 样本 {{ formatCount(detailResult.snapshot_stats.is_401_snapshots) }}</p>
                  <p class="subtle-line">
                    额度异常 {{ formatCount(detailResult.snapshot_stats.invalid_quota_snapshots) }}
                  </p>
                </div>
              </div>

              <div class="panel-grid sample-grid">
                <article class="panel sample-panel">
                  <div class="panel-heading">
                    <div>
                      <p class="section-kicker">失败样本</p>
                      <h3>最近异常快照</h3>
                    </div>
                  </div>
                  <div v-if="detailResult.recent_failure_samples.length" class="event-stack">
                    <article
                      v-for="sample in detailResult.recent_failure_samples"
                      :key="sample.id"
                      class="snapshot-brief"
                    >
                      <div class="event-card-head">
                        <div>
                          <p class="event-title">{{ sample.account.name }}</p>
                          <p class="subtle-line">
                            {{ sample.account.auth_index }} · {{ formatDateTime(sample.checked_at) }}
                          </p>
                        </div>
                        <div class="status-stack">
                          <StatusPill :tone="sampleTone(sample)" :text="sample.snapshot_status" />
                          <StatusPill v-if="sample.account.disabled" tone="muted" text="disabled" />
                        </div>
                      </div>
                      <p class="subtle-line">{{ quotaSummary(sample) }}</p>
                      <p>{{ sample.error_message || sample.status_message || "无额外错误文案" }}</p>
                    </article>
                  </div>
                  <p v-else class="feedback">这一轮没有失败或部分失败快照。</p>
                </article>

                <article class="panel sample-panel">
                  <div class="panel-heading">
                    <div>
                      <p class="section-kicker">风险样本</p>
                      <h3>401 与额度异常</h3>
                    </div>
                  </div>

                  <div class="sample-column">
                    <div>
                      <p class="subtle-label">最近 401 样本</p>
                      <div v-if="detailResult.recent_401_samples.length" class="event-stack">
                        <article
                          v-for="sample in detailResult.recent_401_samples"
                          :key="sample.id"
                          class="snapshot-brief"
                        >
                          <div class="event-card-head">
                            <div>
                              <p class="event-title">{{ sample.account.name }}</p>
                              <p class="subtle-line">{{ formatDateTime(sample.checked_at) }}</p>
                            </div>
                            <StatusPill tone="danger" text="401" />
                          </div>
                          <p>{{ sample.account.provider || "未标注 provider" }} · {{ sample.account.account_type || "未标注类型" }}</p>
                        </article>
                      </div>
                      <p v-else class="feedback">这一轮没有 401 样本。</p>
                    </div>

                    <div>
                      <p class="subtle-label">最近额度异常样本</p>
                      <div v-if="detailResult.recent_quota_samples.length" class="event-stack">
                        <article
                          v-for="sample in detailResult.recent_quota_samples"
                          :key="sample.id"
                          class="snapshot-brief"
                        >
                          <div class="event-card-head">
                            <div>
                              <p class="event-title">{{ sample.account.name }}</p>
                              <p class="subtle-line">{{ formatDateTime(sample.checked_at) }}</p>
                            </div>
                            <StatusPill tone="warning" text="quota" />
                          </div>
                          <p class="subtle-line">{{ quotaSummary(sample) }}</p>
                          <p>{{ sample.status_message || sample.error_message || "无额外提示" }}</p>
                        </article>
                      </div>
                      <p v-else class="feedback">这一轮没有额度异常样本。</p>
                    </div>
                  </div>
                </article>
              </div>
            </template>
          </div>
        </article>
      </div>

      <div class="pager">
        <button class="ghost-button" type="button" :disabled="offset === 0" @click="previousPage">上一页</button>
        <button
          class="ghost-button"
          type="button"
          :disabled="offset + pageSize >= result.total"
          @click="nextPage"
        >
          下一页
        </button>
      </div>
    </template>
  </section>
</template>
