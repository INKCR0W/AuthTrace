<script setup lang="ts">
defineProps<{
  tone: "success" | "danger" | "warning" | "muted";
  text: string;
}>();
</script>

<template>
  <span class="status-pill" :data-tone="tone">{{ text }}</span>
</template>
