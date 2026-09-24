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
  total_active_value: string;
};

const contractsApiBase =
  process.env.NEXT_PUBLIC_CONTRACTS_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8010/api/v1";

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${contractsApiBase}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
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
