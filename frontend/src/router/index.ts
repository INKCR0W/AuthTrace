import { createRouter, createWebHistory } from "vue-router";


const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "dashboard",
      component: () => import("@/pages/DashboardPage.vue"),
    },
    {
      path: "/accounts",
      name: "accounts",
      component: () => import("@/pages/AccountsPage.vue"),
    },
    {
      path: "/events",
      name: "events",
      component: () => import("@/pages/EventsPage.vue"),
    },
    {
      path: "/scan-jobs",
      name: "scan-jobs",
      component: () => import("@/pages/ScanJobsPage.vue"),
    },
    {
      path: "/accounts/:accountId",
      name: "account-detail",
      component: () => import("@/pages/AccountDetailPage.vue"),
    },
  ],
});

export default router;
