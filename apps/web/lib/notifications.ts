import { ApiError } from "./api";

const gatewayBaseUrl =
  process.env.NEXT_PUBLIC_GATEWAY_URL?.replace(/\/$/, "") ?? "http://localhost:8080";
const baseUrl = `${gatewayBaseUrl}/api/v1/notifications`;

export type NotificationStatus = "UNREAD" | "READ" | "ARCHIVED";
export type NotificationSeverity = "INFO" | "SUCCESS" | "WARNING" | "CRITICAL";
export type NotificationItem = {
  id: string; category: string; severity: NotificationSeverity; title: string; body: string;
  resource_type: string | null; resource_id: string | null; resource_url: string | null;
  status: NotificationStatus; read_at: string | null; archived_at: string | null; created_at: string;
};
export type NotificationPage = { items: NotificationItem[]; total: number; limit: number; offset: number };
export type NotificationPreference = {
  id: string; category: string; channel: "IN_APP" | "EMAIL" | "WEBHOOK"; enabled: boolean;
  quiet_hours_start: string | null; quiet_hours_end: string | null; updated_at: string;
};

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event("govcontrol:session-expired"));
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string"
      ? body.detail
      : `API request failed (${response.status})`;
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

export async function notificationsGet<T>(path = ""): Promise<T> {
  return parse<T>(await fetch(`${baseUrl}${path}`, {
    credentials: "include", cache: "no-store",
  }));
}

async function mutate<T>(
  method: "POST" | "PUT" | "PATCH", path: string, csrfToken: string, body: unknown = {},
): Promise<T> {
  return parse<T>(await fetch(`${baseUrl}${path}`, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body),
  }));
}

export const notificationsPatch = <T>(path: string, token: string, body: unknown = {}) =>
  mutate<T>("PATCH", path, token, body);
export const notificationsPost = <T>(path: string, token: string, body: unknown = {}) =>
  mutate<T>("POST", path, token, body);
export const notificationsPut = <T>(path: string, token: string, body: unknown) =>
  mutate<T>("PUT", path, token, body);
