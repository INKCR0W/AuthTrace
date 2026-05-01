<script setup lang="ts">
import { LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { formatDateTime, formatPercent, formatStatusCode } from "@/lib/format";
import type { AccountSnapshotSummary } from "@/types/api";


use([LineChart, ScatterChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

type ChartPoint = {
  checkedAt: string;
  weekly: number | null;
  short: number | null;
  is401: boolean;
  statusCode: number | null;
  snapshotStatus: string;
};

const props = defineProps<{
  snapshots: AccountSnapshotSummary[];
}>();

const chartRoot = ref<HTMLElement | null>(null);

const points = computed<ChartPoint[]>(() => props.snapshots.map((snapshot) => ({
  checkedAt: snapshot.checked_at,
  weekly: toNumber(snapshot.weekly_used_percent),
  short: toNumber(snapshot.short_used_percent),
  is401: snapshot.is_401,
  statusCode: snapshot.probe_status_code,
  snapshotStatus: snapshot.snapshot_status,
})));

let chart: ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;

function toNumber(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatAxisTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function markerValue(point: ChartPoint) {
  return point.weekly ?? point.short ?? (point.is401 ? 100 : null);
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
      bottom: 36,
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
        const dataIndex = typeof first?.dataIndex === "number" ? first.dataIndex : 0;
        const point = points.value[dataIndex];

        if (!point) {
          return "";
        }

        const lines = [
          `<strong>${formatDateTime(point.checkedAt)}</strong>`,
          `状态码：${formatStatusCode(point.statusCode)}`,
          `周额度：${formatPercent(point.weekly)}`,
          `短周期：${formatPercent(point.short)}`,
          `401：${point.is401 ? "是" : "否"}`,
          `快照状态：${point.snapshotStatus}`,
        ];

        return lines.join("<br/>");
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
      data: points.value.map((point) => point.checkedAt),
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
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
        formatter: (value: number) => `${value}%`,
      },
    },
    series: [
      {
        name: "周额度",
        type: "line",
        smooth: true,
        connectNulls: true,
        symbol: "circle",
        symbolSize: 7,
        data: points.value.map((point) => point.weekly),
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
        name: "短周期",
        type: "line",
        smooth: true,
        connectNulls: true,
        symbol: "diamond",
        symbolSize: 7,
        data: points.value.map((point) => point.short),
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
      {
        name: "401 节点",
        type: "scatter",
        symbolSize: 12,
        data: points.value.map((point) => point.is401 ? markerValue(point) : null),
        itemStyle: {
          color: "#a33d4d",
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
  () => props.snapshots,
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
  <div ref="chartRoot" class="chart-root chart-root-tall" />
</template>
