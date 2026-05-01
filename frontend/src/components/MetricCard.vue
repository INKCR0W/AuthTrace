<script setup lang="ts">
defineProps<{
  label: string;
  value: string | number;
  accent?: "sun" | "teal" | "ink" | "rose";
  hint?: string;
}>();
</script>

<template>
  <article class="metric-card" :data-accent="accent ?? 'ink'">
    <p class="metric-label">{{ label }}</p>
    <p class="metric-value">{{ value }}</p>
    <p v-if="hint" class="metric-hint">{{ hint }}</p>
  </article>
</template>
