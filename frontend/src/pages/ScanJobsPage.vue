<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import {
  ApiError,
  getDefaultManagementSource,
  getScanJobDetail,
  getScanJobs,
  triggerAuthFileSync,
} from "@/api/client";
import JsonPayloadViewer from "@/components/JsonPayloadViewer.vue";
import StatusPill from "@/components/StatusPill.vue";
import { formatCount, formatDateTime, formatDurationMs, formatPercent } from "@/lib/format";
import type {
  AuthFileSyncConflictDetail,
  DefaultManagementSourceResponse,
  ScanJobDetailResponse,
  ScanJobListResponse,
  ScanJobSnapshotSample,
} from "@/types/api";


type FeedbackTone = "success" | "warning" | "danger" | "muted";

const pageSize = 20;
const loading = ref(false);
const error = ref("");
const result = ref<ScanJobListResponse | null>(null);
const offset = ref(0);
const selectedJobId = ref<number | null>(null);
const detailLoading = ref(false);
const detailError = ref("");
const detailResult = ref<ScanJobDetailResponse | null>(null);
const sourceLoading = ref(false);
const sourceError = ref("");
const source = ref<DefaultManagementSourceResponse | null>(null);
const syncLoading = ref(false);
const syncFeedback = ref("");
const syncFeedbackTone = ref<FeedbackTone>("muted");
let detailRequestToken = 0;

const filters = reactive({
  status: "",
  trigger_mode: "",
});

async function loadManagementSource() {
  sourceLoading.value = true;
  sourceError.value = "";

  try {
    source.value = await getDefaultManagementSource();
  } catch (requestError) {
    source.value = null;
    sourceError.value = requestError instanceof Error ? requestError.message : "加载管理端配置失败";
  } finally {
    sourceLoading.value = false;
  }
}

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

function sourceScopeSummary() {
  if (!source.value) {
    return "正在等待来源配置...";
  }

  const segments = [`source_key=${source.value.source_key}`];
  if (source.value.target_type) {
    segments.push(`type=${source.value.target_type}`);
  }
  if (source.value.provider) {
    segments.push(`provider=${source.value.provider}`);
  }
  if (segments.length === 1) {
    segments.push("未设置额外筛选");
  }
  return segments.join(" / ");
}

function sourceConfigHint() {
  if (!source.value || source.value.configured) {
    return "";
  }
  if (source.value.base_url) {
    return "管理端地址已存在，但当前缺少完整鉴权配置；补齐 backend/.env 中的 AUTHTRACE_MANAGEMENT_TOKEN 后再执行扫描。";
  }
  return "当前还未配置管理端地址；请先补齐 backend/.env 中的 AUTHTRACE_MANAGEMENT_BASE_URL 与 AUTHTRACE_MANAGEMENT_TOKEN。";
}

function schedulerTone() {
  if (!source.value?.scheduler_enabled) {
    return "muted";
  }
  if (source.value.scheduler_running) {
    return "success";
  }
  if (source.value.scheduler_last_status === "blocked" || source.value.scheduler_last_status === "failed") {
    return "warning";
  }
  return "muted";
}

function schedulerStatusText() {
  if (!source.value?.scheduler_enabled) {
    return "未启用";
  }
  if (source.value.scheduler_running) {
    return "运行中";
  }
  if (source.value.scheduler_last_status === "blocked") {
    return "待补配置";
  }
  if (source.value.scheduler_last_status === "failed") {
    return "最近失败";
  }
  if (source.value.scheduler_last_status === "skipped_conflict") {
    return "遇到冲突";
  }
  return "未启动";
}

function schedulerSummary() {
  if (!source.value) {
    return "正在等待调度状态...";
  }

  const intervalText = `每 ${formatCount(source.value.scheduler_interval_minutes)} 分钟`;
  const nextRunText = source.value.scheduler_next_run_at
    ? `下次 ${formatDateTime(source.value.scheduler_next_run_at)}`
    : "暂无下次执行时间";
  return `${intervalText} / ${nextRunText}`;
}

function schedulerLastResult() {
  if (!source.value) {
    return "";
  }
  if (source.value.scheduler_last_error_message) {
    return source.value.scheduler_last_error_message;
  }
  if (source.value.scheduler_last_finished_at && source.value.scheduler_last_status) {
    return `最近 ${source.value.scheduler_last_status} 于 ${formatDateTime(source.value.scheduler_last_finished_at)}`;
  }
  return "尚未产生自动扫描记录";
}

function clearTaskFilters() {
  filters.status = "";
  filters.trigger_mode = "";
}

function setSyncFeedback(message: string, tone: FeedbackTone) {
  syncFeedback.value = message;
  syncFeedbackTone.value = tone;
}

function feedbackClass(tone: FeedbackTone) {
  if (tone === "danger") {
    return "error";
  }
  if (tone === "success") {
    return "success";
  }
  if (tone === "warning") {
    return "warning";
  }
  return "";
}

function isSyncConflictDetail(value: unknown): value is AuthFileSyncConflictDetail {
  if (!value || typeof value !== "object") {
    return false;
  }

  const runningScanJobId = Reflect.get(value, "running_scan_job_id");
  const sourceId = Reflect.get(value, "source_id");
  const message = Reflect.get(value, "message");
  const scanStartedAt = Reflect.get(value, "scan_started_at");

  return (
    typeof runningScanJobId === "number" &&
    typeof sourceId === "number" &&
    typeof message === "string" &&
    (typeof scanStartedAt === "string" || scanStartedAt === null)
  );
}

async function triggerScan() {
  if (syncLoading.value) {
    return;
  }

  if (!source.value?.configured) {
    setSyncFeedback(sourceConfigHint() || "管理端配置尚未完成，无法执行扫描。", "warning");
    return;
  }

  syncLoading.value = true;
  setSyncFeedback("", "muted");

  try {
    const response = await triggerAuthFileSync();
    const hasFailure = response.status !== "success" || response.failed_snapshots > 0;
    const feedbackTone: FeedbackTone = hasFailure ? "warning" : "success";
    setSyncFeedback(
      `任务 #${response.scan_job_id} 已完成，状态 ${response.status}；成功快照 ${formatCount(response.successful_snapshots)}，失败快照 ${formatCount(response.failed_snapshots)}。`,
      feedbackTone,
    );

    clearTaskFilters();
    offset.value = 0;
    clearDetailSelection();
    await loadScanJobs();
    await toggleDetail(response.scan_job_id);
  } catch (requestError) {
    if (requestError instanceof ApiError && isSyncConflictDetail(requestError.detail)) {
      const startedAtText = requestError.detail.scan_started_at
        ? formatDateTime(requestError.detail.scan_started_at)
        : "未知时间";
      setSyncFeedback(
        `已有运行中的扫描任务 #${requestError.detail.running_scan_job_id}，开始时间 ${startedAtText}。已为你刷新任务列表，可直接下钻查看。`,
        "warning",
      );
      clearTaskFilters();
      offset.value = 0;
      clearDetailSelection();
      await loadScanJobs();
      await toggleDetail(requestError.detail.running_scan_job_id);
      return;
    }

    if (requestError instanceof ApiError) {
      setSyncFeedback(requestError.message, requestError.status >= 500 ? "danger" : "warning");
      if (requestError.status === 503) {
        await loadManagementSource();
      }
      return;
    }

    setSyncFeedback(requestError instanceof Error ? requestError.message : "触发扫描失败", "danger");
  } finally {
    syncLoading.value = false;
  }
}

onMounted(() => {
  void Promise.all([loadManagementSource(), loadScanJobs()]);
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

    <article class="panel scan-control-panel">
      <div class="panel-heading">
        <div>
          <p class="section-kicker">联调入口</p>
          <h3>管理端配置与手动扫描</h3>
        </div>
        <div class="scan-control-actions">
          <button class="ghost-button" type="button" :disabled="sourceLoading" @click="loadManagementSource">
            {{ sourceLoading ? "刷新配置中..." : "刷新配置" }}
          </button>
          <button
            class="primary-button"
            type="button"
            :disabled="syncLoading || sourceLoading || !source?.configured"
            @click="triggerScan"
          >
            {{ syncLoading ? "扫描执行中..." : "手动执行一轮扫描" }}
          </button>
        </div>
      </div>

      <p v-if="sourceError" class="feedback error">{{ sourceError }}</p>
      <p v-else-if="sourceLoading && !source" class="feedback">正在读取管理端配置...</p>

      <template v-else-if="source">
        <div class="detail-grid scan-control-grid">
          <div>
            <p class="subtle-label">管理端来源</p>
            <p><strong>{{ source.source_name }}</strong></p>
            <p class="subtle-line">{{ source.base_url || "尚未配置 AUTHTRACE_MANAGEMENT_BASE_URL" }}</p>
          </div>
          <div>
            <p class="subtle-label">配置状态</p>
            <div class="status-stack">
              <StatusPill :tone="source.configured ? 'success' : 'warning'" :text="source.configured ? '已配置' : '待补配置'" />
              <StatusPill :tone="source.is_enabled ? 'success' : 'muted'" :text="source.is_enabled ? '已启用' : '未启用'" />
            </div>
            <p class="subtle-line">{{ sourceScopeSummary() }}</p>
          </div>
          <div>
            <p class="subtle-label">自动扫描</p>
            <div class="status-stack">
              <StatusPill :tone="schedulerTone()" :text="schedulerStatusText()" />
              <StatusPill tone="muted" :text="`${source.scheduler_interval_minutes} min`" />
            </div>
            <p class="subtle-line">{{ schedulerSummary() }}</p>
            <p class="subtle-line">{{ schedulerLastResult() }}</p>
          </div>
        </div>

        <p v-if="!source.configured" class="feedback warning">{{ sourceConfigHint() }}</p>
      </template>

      <p v-if="syncFeedback" class="feedback" :class="feedbackClass(syncFeedbackTone)">{{ syncFeedback }}</p>
    </article>

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
              <p class="subtle-line">新增 401 {{ formatCount(item.new_401_events) }}</p>
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
                  <p class="subtle-line">失败快照 {{ formatCount(detailResult.snapshot_stats.failed_snapshots) }}</p>
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
                      <div class="json-viewer-stack">
                        <JsonPayloadViewer title="auth-file 原始 JSON" :payload="sample.raw_auth_file_json" />
                        <JsonPayloadViewer title="usage 原始 JSON" :payload="sample.raw_usage_json" />
                      </div>
                    </article>
                  </div>
                  <p v-else class="feedback">这一轮没有失败或部分失败快照。</p>
                </article>

                <article class="panel sample-panel">
                  <div class="panel-heading">
                    <div>
                      <p class="section-kicker">风险样本</p>
                      <h3>401 与失败观察</h3>
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
                          <div class="json-viewer-stack">
                            <JsonPayloadViewer title="auth-file 原始 JSON" :payload="sample.raw_auth_file_json" />
                            <JsonPayloadViewer title="usage 原始 JSON" :payload="sample.raw_usage_json" />
                          </div>
                        </article>
                      </div>
                      <p v-else class="feedback">这一轮没有 401 样本。</p>
                    </div>

                    <div>
                      <p class="subtle-label">额度观察样本</p>
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
                          <div class="json-viewer-stack">
                            <JsonPayloadViewer title="auth-file 原始 JSON" :payload="sample.raw_auth_file_json" />
                            <JsonPayloadViewer title="usage 原始 JSON" :payload="sample.raw_usage_json" />
                          </div>
                        </article>
                      </div>
                      <p v-else class="feedback">当前口径下不会再把非 401 样本标记为异常。</p>
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
