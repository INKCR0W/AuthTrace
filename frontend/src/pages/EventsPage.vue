<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { RouterLink } from "vue-router";

import { getEvents } from "@/api/client";
import StatusPill from "@/components/StatusPill.vue";
import { formatDateTime, formatPercent, toBooleanQuery } from "@/lib/format";
import type { EventListResponse } from "@/types/api";


const pageSize = 20;
const loading = ref(false);
const error = ref("");
const result = ref<EventListResponse | null>(null);
const offset = ref(0);

const filters = reactive({
  event_type: "",
  provider: "",
  account_type: "",
  current_is_401: "",
});

async function loadEvents() {
  loading.value = true;
  error.value = "";

  try {
    result.value = await getEvents({
      event_type: filters.event_type || undefined,
      provider: filters.provider || undefined,
      account_type: filters.account_type || undefined,
      current_is_401: toBooleanQuery(filters.current_is_401),
      limit: pageSize,
      offset: offset.value,
    });
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "加载事件失败";
  } finally {
    loading.value = false;
  }
}

function previousPage() {
  offset.value = Math.max(0, offset.value - pageSize);
  void loadEvents();
}

function nextPage() {
  if (!result.value || offset.value + pageSize >= result.value.total) {
    return;
  }
  offset.value += pageSize;
  void loadEvents();
}

onMounted(() => {
  void loadEvents();
});
</script>

<template>
  <section class="page-section">
    <div class="section-heading">
      <div>
        <p class="section-kicker">事件回放</p>
        <h2>状态变迁样本</h2>
      </div>
    </div>

    <form class="filter-bar" @submit.prevent="offset = 0; loadEvents()">
      <input v-model="filters.event_type" class="input-field" placeholder="事件类型，例如 became_401" />
      <input v-model="filters.provider" class="input-field" placeholder="provider" />
      <input v-model="filters.account_type" class="input-field" placeholder="账号类型" />
      <select v-model="filters.current_is_401" class="input-field">
        <option value="">当前账号状态</option>
        <option value="true">当前仍为 401</option>
        <option value="false">当前已恢复</option>
      </select>
      <div class="filter-actions">
        <button class="primary-button" type="submit">查询</button>
      </div>
    </form>

    <p v-if="error" class="feedback error">{{ error }}</p>
    <p v-else-if="loading && !result" class="feedback">正在读取事件列表...</p>

    <template v-if="result">
      <div class="event-stack">
        <article v-for="item in result.items" :key="item.event.id" class="event-card">
          <div class="event-card-head">
            <div>
              <p class="event-type">{{ item.event.event_type }}</p>
              <RouterLink class="inline-link event-title" :to="`/accounts/${item.account.id}`">
                {{ item.account.name }}
              </RouterLink>
            </div>
            <StatusPill
              :tone="item.event.to_is_401 ? 'danger' : item.event.to_invalid_quota ? 'warning' : 'success'"
              :text="formatDateTime(item.event.event_time)"
            />
          </div>

          <div class="event-grid">
            <div>
              <p class="subtle-label">账号维度</p>
              <p>{{ item.account.provider || "未标记" }} / {{ item.account.account_type || "未标记" }}</p>
            </div>
            <div>
              <p class="subtle-label">当前快照</p>
              <p>
                状态码 {{ item.related_snapshot.probe_status_code ?? "未记录" }}，周额度
                {{ formatPercent(item.related_snapshot.weekly_used_percent) }}
              </p>
            </div>
            <div>
              <p class="subtle-label">上一快照</p>
              <p v-if="item.previous_snapshot">
                状态码 {{ item.previous_snapshot.probe_status_code ?? "未记录" }}，周额度
                {{ formatPercent(item.previous_snapshot.weekly_used_percent) }}
              </p>
              <p v-else>无上一快照</p>
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
