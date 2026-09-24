export type LegalDashboard = {
  open_obligations: number;
  overdue_obligations: number;
  due_within_seven_days: number;
  overdue_days_total: number;
};

export type LegalObligation = {
  id: string;
  description: string;
  obligation_type: string;
  due_date: string | null;
  status: string;
  responsible_department_id: string | null;
  responsible_user_id: string | null;
  completion_date: string | null;
  created_at: string;
  updated_at: string;
};

export type LegalCase = {
  id: string;
  case_number: string;
  court: string;
  subject: string;
  filing_date: string | null;
  status: string;
};

export type CourtDecision = {
  id: string;
  case_id: string;
  decision_number: string;
  decision_date: string;
  decision_type: string;
};

export type EnforcementProceeding = {
  id: string;
  obligation_id: string;
  file_number: string;
  enforcement_officer: string | null;
  start_date: string;
  status: string;
};

export type PenaltyRule = {
  id: string;
  obligation_id: string;
  calculation_type: string;
  daily_amount: string | null;
  percentage: string | null;
  base_value: string | null;
  start_date: string;
  end_date: string | null;
};

export type PenaltyExposure = { rule_id: string; as_of_date: string; amount: string };

export type DocumentRecord = {
  id: string;
  entity_type: string;
  entity_id: string;
  category: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type AuditEvent = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  created_at: string;
};

export type AuditEventPage = { items: AuditEvent[]; limit: number; offset: number };

export type Notification = {
  id: string;
  title: string;
  body: string;
  due_date: string | null;
  status: "UNREAD" | "READ";
  created_at: string;
};

export type AuthenticatedUser = {
  id: string;
  tenant_id: string;
  department_id: string | null;
  email: string;
  display_name: string;
  roles: string[];
  permissions: string[];
};

export type CountDataPoint = { key: string; label: string; value: number };
export type MonthlyActivityPoint = {
  month: string;
  created: number;
  completed: number;
  active_at_end: number;
};
export type WorkloadDataPoint = {
  id: string | null;
  label: string;
  active: number;
  overdue: number;
  completed: number;
};
export type ExposureDataPoint = {
  id: string | null;
  label: string;
  amount: string;
  rules: number;
};
export type LegalAnalytics = {
  generated_on: string;
  filters: {
    period: { date_from: string; date_to: string };
    department_id: string | null;
    responsible_user_id: string | null;
    court: string | null;
    status: string | null;
  };
  kpis: {
    active_obligations: number;
    overdue_obligations: number;
    due_within_seven_days: number;
    active_enforcements: number;
    financial_exposure: string;
    completion_rate: number;
  };
  deadline_distribution: CountDataPoint[];
  overdue_ageing: CountDataPoint[];
  monthly_activity: MonthlyActivityPoint[];
  exposure_by_department: ExposureDataPoint[];
  workload_by_department: WorkloadDataPoint[];
  workload_by_user: WorkloadDataPoint[];
  enforcement_statuses: CountDataPoint[];
};

export type AnalyticsFilterOptions = {
  departments: Array<{ id: string | null; department_id: string | null; label: string; value: string }>;
  users: Array<{ id: string | null; department_id: string | null; label: string; value: string }>;
  courts: Array<{ id: string | null; department_id: string | null; label: string; value: string }>;
  statuses: Array<{ id: string | null; department_id: string | null; label: string; value: string }>;
};

export type LegalSearchResult = {
  id: string;
  entity_type: string;
  title: string;
  summary: string;
  status: string;
  due_date: string | null;
};

export type LegalSearchResponse = { results: LegalSearchResult[] };

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000/api/v1";

export async function apiGet<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `API request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function apiPatch<T>(path: string, token: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `API request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, token: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `API request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function apiUpload<T>(path: string, token: string, body: FormData): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `API request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function apiDownload(path: string, token: string): Promise<Blob> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `API request failed (${response.status})`);
  }
  return response.blob();
}

export function buildQuery(values: Record<string, string | null | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value) query.set(key, value);
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}
