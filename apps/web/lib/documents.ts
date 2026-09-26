export type DocumentState = "QUARANTINED" | "SCANNING" | "AVAILABLE" | "REJECTED";

export type DocumentLink = {
  id: string;
  resource_type: string;
  resource_id: string;
  created_at: string;
};

export type DocumentVersion = {
  id: string;
  version_number: number;
  original_filename: string;
  safe_filename: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string;
  state: DocumentState;
  rejection_reason: string | null;
  created_by_user_id: string;
  created_at: string;
  scanned_at: string | null;
};

export type DocumentRecord = {
  id: string;
  tenant_id: string;
  category: string;
  classification: string;
  retention_until: string | null;
  state: DocumentState;
  current_version_number: number;
  lock_version: number;
  created_by_user_id: string;
  archived_at: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
  current_version: DocumentVersion;
  links: DocumentLink[];
  entity_type: string;
  entity_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string;
};

export type DocumentPage = {
  items: DocumentRecord[];
  total: number;
  page: number;
  page_size: number;
};

export type DocumentAuditEvent = {
  id: string;
  document_id: string;
  actor_user_id: string;
  action: string;
  request_id: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
};

const gatewayBaseUrl =
  process.env.NEXT_PUBLIC_GATEWAY_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8080";
const documentsApiBase = `${gatewayBaseUrl}/api/v1/documents`;

async function documentError(response: Response): Promise<Error> {
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event("govcontrol:session-expired"));
  }
  const payload = await response.json().catch(() => null);
  const detail = typeof payload?.detail === "string" ? payload.detail : null;
  if (response.status === 403) return new Error(detail ?? "Nu ai permisiunea necesară pentru documente.");
  return new Error(detail ?? `Cererea GovDocuments a eșuat (${response.status}).`);
}

async function request<T>(path: string, csrfToken: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${documentsApiBase}${path}`, {
    ...init,
    credentials: "include",
    cache: "no-store",
    headers: {
      ...(init?.method && init.method !== "GET" ? { "X-CSRF-Token": csrfToken } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) throw await documentError(response);
  return response.json() as Promise<T>;
}

function flatten(record: Omit<DocumentRecord, "entity_type" | "entity_id" | "original_filename" | "content_type" | "size_bytes" | "checksum_sha256">): DocumentRecord {
  const primaryLink = record.links[0];
  return {
    ...record,
    entity_type: primaryLink?.resource_type ?? "Unlinked",
    entity_id: primaryLink?.resource_id ?? "",
    original_filename: record.current_version.original_filename,
    content_type: record.current_version.content_type,
    size_bytes: record.current_version.size_bytes,
    checksum_sha256: record.current_version.checksum_sha256,
  };
}

type DocumentApiRecord = Omit<DocumentRecord, "entity_type" | "entity_id" | "original_filename" | "content_type" | "size_bytes" | "checksum_sha256">;

export async function documentsList(
  csrfToken: string,
  filters?: { resource_type?: string; resource_id?: string; query?: string; include_deleted?: boolean },
): Promise<DocumentPage> {
  const query = new URLSearchParams();
  if (filters?.resource_type) query.set("resource_type", filters.resource_type);
  if (filters?.resource_id) query.set("resource_id", filters.resource_id);
  if (filters?.query) query.set("query", filters.query);
  if (filters?.include_deleted) query.set("include_deleted", "true");
  query.set("page_size", "100");
  const response = await request<{ items: DocumentApiRecord[]; total: number; page: number; page_size: number }>(
    `?${query.toString()}`,
    csrfToken,
  );
  return { ...response, items: response.items.map(flatten) };
}

export async function documentsGet(documentId: string, csrfToken: string): Promise<DocumentRecord> {
  return flatten(await request<DocumentApiRecord>(`/${documentId}`, csrfToken));
}

export async function documentsVersions(
  documentId: string,
  csrfToken: string,
): Promise<DocumentVersion[]> {
  return request<DocumentVersion[]>(`/${documentId}/versions`, csrfToken);
}

export async function documentsAudit(
  documentId: string,
  csrfToken: string,
): Promise<DocumentAuditEvent[]> {
  return request<DocumentAuditEvent[]>(`/${documentId}/audit`, csrfToken);
}

export async function documentsUpload(
  csrfToken: string,
  body: FormData,
  idempotencyKey = crypto.randomUUID(),
): Promise<DocumentRecord> {
  if (body.has("entity_type")) {
    body.set("resource_type", String(body.get("entity_type")));
    body.delete("entity_type");
  }
  if (body.has("entity_id")) {
    body.set("resource_id", String(body.get("entity_id")));
    body.delete("entity_id");
  }
  return flatten(await request<DocumentApiRecord>("", csrfToken, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body,
  }));
}

export async function documentsAddVersion(
  documentId: string,
  file: File,
  lockVersion: number,
  csrfToken: string,
): Promise<DocumentRecord> {
  const body = new FormData();
  body.set("file", file);
  return flatten(await request<DocumentApiRecord>(`/${documentId}/versions`, csrfToken, {
    method: "POST",
    headers: { "If-Match": `"${lockVersion}"` },
    body,
  }));
}

export async function documentsDownload(
  documentId: string,
  csrfToken: string,
  version?: number,
): Promise<Blob> {
  const suffix = version ? `?version=${version}` : "";
  const response = await fetch(`${documentsApiBase}/${documentId}/download${suffix}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) throw await documentError(response);
  return response.blob();
}

export async function documentsAction(
  documentId: string,
  action: "archive" | "restore" | "delete",
  csrfToken: string,
): Promise<DocumentRecord> {
  const path = action === "delete" ? `/${documentId}` : `/${documentId}/${action}`;
  return flatten(await request<DocumentApiRecord>(path, csrfToken, {
    method: action === "delete" ? "DELETE" : "POST",
  }));
}
