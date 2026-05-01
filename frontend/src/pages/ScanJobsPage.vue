<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import { getScanJobs } from "@/api/client";
import StatusPill from "@/components/StatusPill.vue";
import { formatCount, formatDateTime, formatDurationMs } from "@/lib/format";
import type { ScanJobListResponse } from "@/types/api";


const pageSize = 20;
const loading = ref(false);
const error = ref("");
const result = ref<ScanJobListResponse | null>(null);
const offset = ref(0);

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

function resetFilters() {
  filters.status = "";
  filters.trigger_mode = "";
  offset.value = 0;
  void loadScanJobs();
}

function previousPage() {
  offset.value = Math.max(0, offset.value - pageSize);
  void loadScanJobs();
}

function nextPage() {
  if (!result.value || offset.value + pageSize >= result.value.total) {
    return;
  }
  offset.value += pageSize;
  void loadScanJobs();
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

    <form class="filter-bar scan-job-filter-bar" @submit.prevent="offset = 0; loadScanJobs()">
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
