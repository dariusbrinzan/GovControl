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

export type InstitutionDirectory = {
  departments: Array<{ id: string; name: string; code: string | null; parent_department_id: string | null }>;
  users: Array<{ id: string; display_name: string; email: string; department_id: string | null }>;
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

const gatewayBaseUrl =
  process.env.NEXT_PUBLIC_GATEWAY_URL?.replace(/\/$/, "") ?? "http://localhost:8080";
const apiBaseUrl = `${gatewayBaseUrl}/api/v1/platform`;

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function sessionExpired(response: Response) {
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event("govcontrol:session-expired"));
  }
}

async function responseError(response: Response, notifySession = true): Promise<ApiError> {
  if (notifySession) sessionExpired(response);
  const body = await response.json().catch(() => null);
  return new ApiError(body?.detail ?? `API request failed (${response.status})`, response.status);
}

export type GatewaySession = {
  user: AuthenticatedUser;
  csrf_token: string;
  expires_at: string;
  auth_method: "local" | "oidc";
};

export async function gatewayAuthConfig(): Promise<{ mode: "local" | "oidc"; login_url: string }> {
  const response = await fetch(`${gatewayBaseUrl}/auth/config`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) throw await responseError(response, false);
  return response.json() as Promise<{ mode: "local" | "oidc"; login_url: string }>;
}

export async function gatewaySession(): Promise<GatewaySession> {
  const response = await fetch(`${gatewayBaseUrl}/auth/session`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) throw await responseError(response, false);
  return response.json() as Promise<GatewaySession>;
}

export async function gatewayLocalLogin(): Promise<GatewaySession> {
  const response = await fetch(`${gatewayBaseUrl}/auth/local/login`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<GatewaySession>;
}

export function gatewayLoginUrl(): string {
  return `${gatewayBaseUrl}/auth/login`;
}

export async function gatewayLogout(csrfToken: string): Promise<void> {
  const response = await fetch(`${gatewayBaseUrl}/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!response.ok) throw await responseError(response);
}

export async function apiGet<T>(path: string, _csrfToken: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

export async function apiPatch<T>(path: string, csrfToken: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, csrfToken: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

export function buildQuery(values: Record<string, string | null | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value) query.set(key, value);
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}
