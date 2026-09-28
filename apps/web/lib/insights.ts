import { ApiError } from "./api";

const gatewayBaseUrl =
  process.env.NEXT_PUBLIC_GATEWAY_URL?.replace(/\/$/, "") ??
  "http://localhost:8080";
const insightsBaseUrl = `${gatewayBaseUrl}/api/v1/insights`;

export type CountBucket = { key: string; count: number };
export type MoneyBucket = {
  currency: string;
  category: string;
  amount: string;
};
export type MonthBucket = { month: string; count: number };
export type InsightsDashboard = {
  module: string | null;
  total: number;
  by_status: CountBucket[];
  by_type: CountBucket[];
  workload_by_department: CountBucket[];
  workload_by_responsible: CountBucket[];
  financial_exposure: MoneyBucket[];
  monthly_trend: MonthBucket[];
  period_total: number;
  previous_period_total: number;
  period_change_percent: number | null;
  overdue: number;
  due_soon_7: number;
  due_soon_30: number;
  due_soon_60: number;
  due_soon_90: number;
  projection_version: number;
  last_updated_at: string | null;
  stale: boolean;
};

export type InsightsSearchItem = {
  id: string;
  module: string;
  resource_type: string;
  source_id: string;
  identifier: string | null;
  display_label: string | null;
  status: string | null;
  source_url: string;
  rank: number;
  updated_at: string;
};

export type InsightsSearchPage = {
  items: InsightsSearchItem[];
  total: number;
  limit: number;
  offset: number;
};

export type InsightsMetadata = {
  modules: string[];
  report_columns: string[];
  report_resource_types: string[];
};
export type SavedReport = {
  id: string;
  owner_user_id: string;
  name: string;
  description: string | null;
  resource_type: string;
  filters: Record<string, string>;
  columns: string[];
  sort: Array<{ column: string; direction: "asc" | "desc" }>;
  shared_with_roles: string[];
  created_at: string;
  updated_at: string;
};
export type ReportRun = {
  id: string;
  report_id: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  row_count: number | null;
  error_code: string | null;
  requested_at: string;
  started_at: string | null;
  completed_at: string | null;
};
export type ExportArtifact = {
  id: string;
  run_id: string;
  format: "csv" | "xlsx";
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  size_bytes: number | null;
  expires_at: string;
  created_at: string;
};

async function errorFrom(response: Response): Promise<ApiError> {
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event("govcontrol:session-expired"));
  }
  const body = await response.json().catch(() => null);
  const detail =
    typeof body?.detail === "string"
      ? body.detail
      : `Cererea a eșuat (${response.status}).`;
  return new ApiError(detail, response.status);
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  csrfToken?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`${insightsBaseUrl}${path}`, {
    ...options,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) throw await errorFrom(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function insightsGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function insightsPost<T>(
  path: string,
  csrfToken: string,
  body: unknown,
): Promise<T> {
  return request<T>(
    path,
    { method: "POST", body: JSON.stringify(body) },
    csrfToken,
  );
}

export function insightsPut<T>(
  path: string,
  csrfToken: string,
  body: unknown,
): Promise<T> {
  return request<T>(
    path,
    { method: "PUT", body: JSON.stringify(body) },
    csrfToken,
  );
}

export function insightsDelete(path: string, csrfToken: string): Promise<void> {
  return request<void>(path, { method: "DELETE" }, csrfToken);
}

export function exportDownloadUrl(exportId: string): string {
  return `${insightsBaseUrl}/exports/${encodeURIComponent(exportId)}/download`;
}
