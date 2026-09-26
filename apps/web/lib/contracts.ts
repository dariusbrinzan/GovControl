export type ContractStatus =
  | "DRAFT"
  | "IN_REVIEW"
  | "ACTIVE"
  | "SUSPENDED"
  | "COMPLETED"
  | "TERMINATED"
  | "CANCELLED";

export type ContractRecord = {
  id: string;
  tenant_id: string;
  contract_number: string;
  title: string;
  description: string | null;
  value: string;
  currency: string;
  signed_date: string | null;
  start_date: string;
  end_date: string;
  status: ContractStatus;
  responsible_department_id: string | null;
  responsible_user_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type ContractDashboard = {
  total_contracts: number;
  active_contracts: number;
  expiring_within_30_days: number;
  status_counts: Partial<Record<ContractStatus, number>>;
  active_value_by_currency: Record<string, string>;
};
export type ContractPage = { items: ContractRecord[]; total: number; limit: number; offset: number };

export type ContractParty = {
  id: string; name: string; registration_number: string | null; party_type: string;
  email: string | null; phone: string | null; address: string | null; role: string | null;
};
export type ContractAmendment = {
  id: string; amendment_number: string; signed_date: string; value_change: string | null;
  end_date_change: string | null; description: string; created_at: string;
};
export type ContractMilestone = {
  id: string; title: string; due_date: string; status: MilestoneStatus; completed_at: string | null;
};
export type ContractObligation = {
  id: string; description: string; due_date: string | null; status: ObligationStatus;
  responsible_user_id: string | null;
};
export type ContractPayment = {
  id: string; amount: string; currency: string; due_date: string; paid_date: string | null;
  status: PaymentStatus; reference: string | null;
};
export type MilestoneStatus = "PENDING" | "IN_PROGRESS" | "COMPLETED" | "OVERDUE" | "CANCELLED";
export type ObligationStatus = "OPEN" | "IN_PROGRESS" | "COMPLETED" | "OVERDUE" | "CANCELLED";
export type PaymentStatus = "PLANNED" | "APPROVED" | "PAID" | "REJECTED" | "CANCELLED";
export type ContractDetail = {
  contract: ContractRecord;
  parties: ContractParty[];
  amendments: ContractAmendment[];
  milestones: ContractMilestone[];
  obligations: ContractObligation[];
  payments: ContractPayment[];
};
export type ContractNotification = {
  id: string; entity_type: string; entity_id: string; notification_type: string;
  title: string; body: string; due_date: string | null; read_at: string | null; created_at: string;
};
export type ContractAuditEvent = {
  id: string; actor_user_id: string; action: string; entity_type: string; entity_id: string;
  payload: Record<string, unknown> | null; request_id: string | null; created_at: string;
};
export type ContractAuditPage = {
  items: ContractAuditEvent[]; total: number; limit: number; offset: number;
};

const contractsApiBase =
  `${process.env.NEXT_PUBLIC_GATEWAY_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8080"}/api/v1/govcontracts`;

async function request<T>(path: string, csrfToken: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${contractsApiBase}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.method && init.method !== "GET" ? { "X-CSRF-Token": csrfToken } : {}),
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event("govcontrol:session-expired"));
    }
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `GovContracts request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function contractsGet<T>(path: string, token: string): Promise<T> {
  return request<T>(path, token);
}

export function contractsPost<T>(path: string, token: string, body: unknown): Promise<T> {
  return request<T>(path, token, { method: "POST", body: JSON.stringify(body) });
}

export function contractsPatch<T>(path: string, token: string, body: unknown): Promise<T> {
  return request<T>(path, token, { method: "PATCH", body: JSON.stringify(body) });
}
