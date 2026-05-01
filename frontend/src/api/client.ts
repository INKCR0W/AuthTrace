import type {
  AccountDetailResponse,
  AccountListResponse,
  DashboardOverviewResponse,
  EventListResponse,
  ScanJobDetailResponse,
  ScanJobListResponse,
} from "@/types/api";


const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

function buildUrl(path: string, query?: Record<string, string | number | boolean | undefined>) {
  const url = new URL(path, `${API_BASE_URL}/`);

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === "") {
        continue;
      }
      url.searchParams.set(key, String(value));
    }
  }

  return url.toString();
}

async function requestJson<T>(path: string, query?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const response = await fetch(buildUrl(path, query), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    const fallbackText = await response.text();
    throw new Error(fallbackText || `请求失败：${response.status}`);
  }

  return (await response.json()) as T;
}

export function getDashboardOverview() {
  return requestJson<DashboardOverviewResponse>("api/v1/dashboard/overview");
}

export function getAccounts(query?: Record<string, string | number | boolean | undefined>) {
  return requestJson<AccountListResponse>("api/v1/accounts", query);
}

export function getEvents(query?: Record<string, string | number | boolean | undefined>) {
  return requestJson<EventListResponse>("api/v1/events", query);
}

export function getAccountDetail(accountId: number, query?: Record<string, string | number | boolean | undefined>) {
  return requestJson<AccountDetailResponse>(`api/v1/accounts/${accountId}`, query);
}

export function getScanJobs(query?: Record<string, string | number | boolean | undefined>) {
  return requestJson<ScanJobListResponse>("api/v1/scan-jobs", query);
}

export function getScanJobDetail(scanJobId: number) {
  return requestJson<ScanJobDetailResponse>(`api/v1/scan-jobs/${scanJobId}`);
}
