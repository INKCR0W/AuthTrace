<script setup lang="ts">
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { formatDateTime } from "@/lib/format";
import type { AccountCohortTrendPoint } from "@/types/api";


use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  points: AccountCohortTrendPoint[];
}>();

const chartRoot = ref<HTMLElement | null>(null);

const pressureSeries = computed(() => props.points.map((point) => point.high_weekly_count + point.high_short_count));

let chart: ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;

function formatAxisTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

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
      top: 44,
      right: 18,
      bottom: 30,
      left: 44,
    },
    legend: {
      top: 8,
      textStyle: {
        color: "#4b433f",
      },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255, 251, 245, 0.96)",
      borderColor: "rgba(65, 54, 45, 0.12)",
      textStyle: {
        color: "#1f1a17",
      },
      formatter: (params: any) => {
        const first = Array.isArray(params) ? params[0] : params;
        const index = typeof first?.dataIndex === "number" ? first.dataIndex : 0;
        const point = props.points[index];

        if (!point) {
          return "";
        }

        return [
          `<strong>${formatDateTime(point.bucket_start)}</strong>`,
          `同组快照：${point.snapshot_count}`,
          `401 快照：${point.is_401_count}`,
          `额度异常：${point.invalid_quota_count}`,
          `高压信号：${point.high_weekly_count + point.high_short_count}`,
          `失败快照：${point.failed_count}`,
        ].join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      axisLine: {
        lineStyle: { color: "#6b645f" },
      },
      axisLabel: {
        color: "#4b433f",
        formatter: (value: string) => formatAxisTime(value),
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
        name: "401 快照",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 7,
        data: props.points.map((point) => point.is_401_count),
        lineStyle: {
          width: 3,
          color: "#a33d4d",
        },
        itemStyle: {
          color: "#a33d4d",
          borderColor: "#fffaf1",
          borderWidth: 2,
        },
      },
      {
        name: "额度异常",
        type: "line",
        smooth: true,
        symbol: "diamond",
        symbolSize: 7,
        data: props.points.map((point) => point.invalid_quota_count),
        lineStyle: {
          width: 3,
          color: "#d46b2d",
        },
        itemStyle: {
          color: "#d46b2d",
          borderColor: "#fffaf1",
          borderWidth: 2,
        },
      },
      {
        name: "高压信号",
        type: "line",
        smooth: true,
        symbol: "triangle",
        symbolSize: 8,
        data: pressureSeries.value,
        lineStyle: {
          width: 3,
          color: "#0f8b8d",
        },
        itemStyle: {
          color: "#0f8b8d",
          borderColor: "#fffaf1",
          borderWidth: 2,
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
