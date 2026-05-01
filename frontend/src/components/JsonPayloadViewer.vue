<script setup lang="ts">
import { computed } from "vue";

import type { JsonObject } from "@/types/api";


const props = withDefaults(defineProps<{
  title: string;
  payload: JsonObject | null;
  emptyText?: string;
}>(), {
  emptyText: "当前没有原始载荷",
});

const prettyPayload = computed(() => {
  if (!props.payload) {
    return "";
  }
  return JSON.stringify(props.payload, null, 2);
});
</script>

<template>
  <details class="json-viewer" :open="false">
    <summary>{{ title }}</summary>
    <pre v-if="prettyPayload" class="json-code">{{ prettyPayload }}</pre>
    <p v-else class="json-empty">{{ emptyText }}</p>
  </details>
</template>
