<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { RouterLink } from "vue-router";

import { getAccounts } from "@/api/client";
import StatusPill from "@/components/StatusPill.vue";
import { formatDateTime, formatPercent, formatStatusCode, toBooleanQuery } from "@/lib/format";
import type { AccountListResponse } from "@/types/api";


const pageSize = 20;
const loading = ref(false);
const error = ref("");
const result = ref<AccountListResponse | null>(null);
const offset = ref(0);

const filters = reactive({
  provider: "",
  account_type: "",
  current_is_401: "",
  disabled: "",
  include_deleted: false,
});

async function loadAccounts() {
  loading.value = true;
  error.value = "";

  try {
    result.value = await getAccounts({
      provider: filters.provider || undefined,
      account_type: filters.account_type || undefined,
      current_is_401: toBooleanQuery(filters.current_is_401),
      disabled: toBooleanQuery(filters.disabled),
      include_deleted: filters.include_deleted,
      limit: pageSize,
      offset: offset.value,
    });
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "加载账号失败";
  } finally {
    loading.value = false;
  }
}

function resetFilters() {
  filters.provider = "";
  filters.account_type = "";
  filters.current_is_401 = "";
  filters.disabled = "";
  filters.include_deleted = false;
  offset.value = 0;
  void loadAccounts();
}

function previousPage() {
  offset.value = Math.max(0, offset.value - pageSize);
  void loadAccounts();
}

function nextPage() {
  if (!result.value || offset.value + pageSize >= result.value.total) {
    return;
  }
  offset.value += pageSize;
  void loadAccounts();
}

onMounted(() => {
  void loadAccounts();
});
</script>

<template>
  <section class="page-section">
    <div class="section-heading">
      <div>
        <p class="section-kicker">账号索引</p>
        <h2>当前状态列表</h2>
      </div>
    </div>

    <form class="filter-bar" @submit.prevent="offset = 0; loadAccounts()">
      <input v-model="filters.provider" class="input-field" placeholder="provider，例如 openai" />
      <input v-model="filters.account_type" class="input-field" placeholder="类型，例如 chatgpt" />
      <select v-model="filters.current_is_401" class="input-field">
        <option value="">401 状态</option>
        <option value="true">当前 401</option>
        <option value="false">当前非 401</option>
      </select>
      <select v-model="filters.disabled" class="input-field">
        <option value="">禁用状态</option>
        <option value="true">已禁用</option>
        <option value="false">未禁用</option>
      </select>
      <label class="checkbox-field">
        <input v-model="filters.include_deleted" type="checkbox" />
        包含已从源端删除账号
      </label>
      <div class="filter-actions">
        <button class="primary-button" type="submit">查询</button>
        <button class="ghost-button" type="button" @click="resetFilters">重置</button>
      </div>
    </form>

    <p v-if="error" class="feedback error">{{ error }}</p>
    <p v-else-if="loading && !result" class="feedback">正在读取账号列表...</p>

    <template v-if="result">
      <div class="table-meta">
        <span>共 {{ result.total }} 条</span>
        <span>当前偏移 {{ result.offset }}</span>
      </div>

      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>账号</th>
              <th>provider / type</th>
              <th>状态</th>
              <th>额度</th>
              <th>最后检测</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="account in result.items" :key="account.id">
              <td>
                <RouterLink class="inline-link" :to="`/accounts/${account.id}`">
                  {{ account.name }}
                </RouterLink>
                <p class="subtle-line">{{ account.auth_index }}</p>
              </td>
              <td>
                <strong>{{ account.provider || "未标记" }}</strong>
                <p class="subtle-line">{{ account.account_type || "未标记" }}</p>
              </td>
              <td>
                <div class="status-stack">
                  <StatusPill :tone="account.current_is_401 ? 'danger' : 'success'" :text="formatStatusCode(account.current_status_code)" />
                  <StatusPill :tone="account.disabled ? 'muted' : 'success'" :text="account.disabled ? '已禁用' : '活跃'" />
                </div>
              </td>
              <td>
                <strong>周 {{ formatPercent(account.current_weekly_used_percent) }}</strong>
                <p class="subtle-line">短周期 {{ formatPercent(account.current_short_used_percent) }}</p>
              </td>
              <td>{{ formatDateTime(account.current_last_checked_at) }}</td>
            </tr>
          </tbody>
        </table>
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
