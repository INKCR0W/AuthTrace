import type {
  AccountDetailResponse,
  AccountListResponse,
  AuthFileSyncResponse,
  DashboardOverviewResponse,
  DefaultManagementSourceResponse,
  EventListResponse,
  ScanJobDetailResponse,
  ScanJobListResponse,
} from "@/types/api";


const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";
type QueryValue = string | number | boolean | undefined;

interface RequestOptions {
  method?: string;
  query?: Record<string, QueryValue>;
  body?: unknown;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, options: { status: number; detail: unknown }) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.detail = options.detail;
  }
}

function buildUrl(path: string, query?: Record<string, QueryValue>) {
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

function extractErrorMessage(detail: unknown, status: number) {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (detail && typeof detail === "object") {
    const message = Reflect.get(detail, "message");
    if (typeof message === "string" && message.trim()) {
      return message;
    }

    const nestedDetail = Reflect.get(detail, "detail");
    if (typeof nestedDetail === "string" && nestedDetail.trim()) {
      return nestedDetail;
    }
  }

  return `请求失败：${status}`;
}

async function parseErrorDetail(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      const payload = (await response.json()) as { detail?: unknown };
      return payload.detail ?? payload;
    } catch {
      return null;
    }
  }

  try {
    const text = await response.text();
    return text || null;
  } catch {
    return null;
  }
}

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers: {
      Accept: "application/json",
      ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    throw new ApiError(extractErrorMessage(detail, response.status), {
      status: response.status,
      detail,
    });
  }

  return (await response.json()) as T;
}

export function getDashboardOverview() {
  return requestJson<DashboardOverviewResponse>("api/v1/dashboard/overview");
}

export function getAccounts(query?: Record<string, QueryValue>) {
  return requestJson<AccountListResponse>("api/v1/accounts", { query });
}

export function getEvents(query?: Record<string, QueryValue>) {
  return requestJson<EventListResponse>("api/v1/events", { query });
}

export function getAccountDetail(accountId: number, query?: Record<string, QueryValue>) {
  return requestJson<AccountDetailResponse>(`api/v1/accounts/${accountId}`, { query });
}

export function getScanJobs(query?: Record<string, QueryValue>) {
  return requestJson<ScanJobListResponse>("api/v1/scan-jobs", { query });
}

export function getScanJobDetail(scanJobId: number) {
  return requestJson<ScanJobDetailResponse>(`api/v1/scan-jobs/${scanJobId}`);
}

export function getDefaultManagementSource() {
  return requestJson<DefaultManagementSourceResponse>("api/v1/management-sources/default");
}

export function triggerAuthFileSync(trigger_mode = "manual") {
  return requestJson<AuthFileSyncResponse>("api/v1/sync/auth-files", {
    method: "POST",
    body: { trigger_mode },
  });
}
