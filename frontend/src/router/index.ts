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
      path: "/research",
      name: "research",
      component: () => import("@/pages/ResearchPage.vue"),
    },
    {
      path: "/events",
      name: "events",
      component: () => import("@/pages/EventsPage.vue"),
    },
    {
      path: "/events/:eventId",
      name: "event-detail",
      component: () => import("@/pages/EventDetailPage.vue"),
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
