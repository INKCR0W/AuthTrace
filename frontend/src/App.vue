<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from "vue-router";


const route = useRoute();

const navItems = [
  { to: "/", label: "总览", name: "dashboard" },
  { to: "/accounts", label: "账号", name: "accounts" },
  { to: "/events", label: "事件", name: "events" },
  { to: "/scan-jobs", label: "扫描", name: "scan-jobs" },
];
</script>

<template>
  <div class="app-shell">
    <header class="hero-panel">
      <div class="hero-copy">
        <p class="eyebrow">AuthTrace</p>
        <h1>账号状态时序观测台</h1>
        <p class="hero-text">
          聚焦 401、额度异常与状态变迁，把每次扫描结果串成可回看的样本链路。
        </p>
      </div>
      <nav class="nav-tabs" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          class="nav-tab"
          :class="{ active: route.name === item.name }"
          :to="item.to"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
    </header>

    <main class="page-shell">
      <RouterView />
    </main>
  </div>
</template>
