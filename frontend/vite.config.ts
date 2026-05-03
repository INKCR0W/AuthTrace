import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const apiProxyTarget = process.env.VITE_DEV_PROXY_TARGET ?? "http://127.0.0.1:8000";
const apiProxy = {
  "/api": {
    target: apiProxyTarget,
    changeOrigin: true,
  },
  "/health": {
    target: apiProxyTarget,
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          framework: ["vue", "vue-router"],
          charts: [
            "echarts/core",
            "echarts/charts",
            "echarts/components",
            "echarts/renderers",
          ],
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: apiProxy,
  },
  preview: {
    host: "0.0.0.0",
    port: 4173,
    proxy: apiProxy,
  },
});
