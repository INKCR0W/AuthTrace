<script setup lang="ts">
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { graphic, init, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import type { OverviewTrendPoint } from "@/types/api";

use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);


const props = defineProps<{
  points: OverviewTrendPoint[];
}>();

const chartRoot = ref<HTMLElement | null>(null);

let chart: ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;

function renderChart() {
  if (!chartRoot.value) {
    return;
  }

  if (!chart) {
    chart = init(chartRoot.value);
  }

  chart.setOption({
    backgroundColor: "transparent",
    grid: {
      top: 24,
      right: 16,
      bottom: 28,
      left: 40,
    },
    tooltip: {
      trigger: "axis",
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      axisLine: {
        lineStyle: { color: "#6b645f" },
      },
      axisLabel: {
        color: "#4b433f",
        formatter: (value: string) => value.slice(11, 16),
      },
      data: props.points.map((point) => point.bucket_start),
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      axisLine: {
        lineStyle: { color: "#6b645f" },
      },
      splitLine: {
        lineStyle: {
          color: "rgba(107, 100, 95, 0.18)",
        },
      },
      axisLabel: {
        color: "#4b433f",
      },
    },
    series: [
      {
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 7,
        data: props.points.map((point) => point.became_401_count),
        lineStyle: {
          width: 3,
          color: "#d46b2d",
        },
        itemStyle: {
          color: "#0f8b8d",
          borderColor: "#f5efe6",
          borderWidth: 2,
        },
        areaStyle: {
          color: new graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(212, 107, 45, 0.36)" },
            { offset: 1, color: "rgba(15, 139, 141, 0.06)" },
          ]),
        },
      },
    ],
  });
}

onMounted(() => {
  renderChart();

  if (chartRoot.value) {
    resizeObserver = new ResizeObserver(() => {
      chart?.resize();
    });
    resizeObserver.observe(chartRoot.value);
  }
});

watch(
  () => props.points,
  () => {
    renderChart();
  },
  { deep: true },
);

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  chart?.dispose();
});
</script>

<template>
  <div ref="chartRoot" class="chart-root" />
</template>
