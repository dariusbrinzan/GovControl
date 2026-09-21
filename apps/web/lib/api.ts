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
};

export type LegalCase = {
  id: string;
  case_number: string;
  court: string;
  subject: string;
  filing_date: string | null;
  status: string;
};

export type EnforcementProceeding = {
  id: string;
  file_number: string;
  enforcement_officer: string | null;
  start_date: string;
  status: string;
};

export type PenaltyRule = {
  id: string;
  calculation_type: string;
  start_date: string;
  end_date: string | null;
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
