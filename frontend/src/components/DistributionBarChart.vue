<script setup lang="ts">
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { init, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";


use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  labels: string[];
  values: number[];
  seriesName: string;
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
      bottom: 44,
      left: 40,
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "rgba(255, 251, 245, 0.96)",
      borderColor: "rgba(65, 54, 45, 0.12)",
      textStyle: {
        color: "#1f1a17",
      },
    },
    xAxis: {
      type: "category",
      axisLabel: {
        color: "#4b433f",
        interval: 0,
        rotate: props.labels.length > 8 ? 18 : 0,
      },
      axisLine: {
        lineStyle: { color: "#6b645f" },
      },
      data: props.labels,
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      axisLabel: {
        color: "#4b433f",
      },
      axisLine: {
        lineStyle: { color: "#6b645f" },
      },
      splitLine: {
        lineStyle: {
          color: "rgba(107, 100, 95, 0.18)",
        },
      },
    },
    series: [
      {
        name: props.seriesName,
        type: "bar",
        barMaxWidth: 28,
        data: props.values,
        itemStyle: {
          color: "#d46b2d",
          borderRadius: [10, 10, 0, 0],
        },
        emphasis: {
          itemStyle: {
            color: "#a33d4d",
          },
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
  () => [props.labels, props.values, props.seriesName],
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
