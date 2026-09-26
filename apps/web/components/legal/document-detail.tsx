"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  documentsAction,
  documentsAddVersion,
  documentsAudit,
  documentsDownload,
  documentsGet,
  documentsVersions,
  type DocumentAuditEvent,
  type DocumentRecord,
  type DocumentVersion,
} from "../../lib/documents";
import { formatDate } from "../../lib/legal";
import { Archive } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { StatusBadge } from "../ui/status-badge";
import { useSession } from "./session-provider";

export function DocumentDetail({ id }: { id: string }) {
  const { token, user, ready } = useSession();
  const [document, setDocument] = useState<DocumentRecord | null>(null);
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [audit, setAudit] = useState<DocumentAuditEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!token) return;
    setBusy(true); setError(null);
    try {
      const [record, versionItems, auditItems] = await Promise.all([
        documentsGet(id, token), documentsVersions(id, token), documentsAudit(id, token),
      ]);
      setDocument(record); setVersions(versionItems); setAudit(auditItems);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Documentul nu a putut fi încărcat."); }
    finally { setBusy(false); }
  }, [id, token]);
  useEffect(() => { void load(); }, [load]);

  const download = async (version: DocumentVersion) => {
    if (!document) return;
    setBusy(true); setError(null);
    try {
      const blob = await documentsDownload(document.id, token, version.version_number);
      const url = URL.createObjectURL(blob); const anchor = window.document.createElement("a");
      anchor.href = url; anchor.download = version.safe_filename; anchor.click(); URL.revokeObjectURL(url);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Versiunea nu a putut fi descărcată."); }
    finally { setBusy(false); }
  };
  const addVersion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!document) return;
    const form = event.currentTarget; const file = new FormData(form).get("file");
    if (!(file instanceof File) || !file.size) return;
    setBusy(true); setError(null);
    try { await documentsAddVersion(document.id, file, document.lock_version, token); form.reset(); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Versiunea nu a putut fi creată."); }
    finally { setBusy(false); }
  };
  const lifecycle = async (action: "archive" | "restore" | "delete") => {
    if (!document) return;
    setBusy(true); setError(null);
    try { setDocument(await documentsAction(document.id, action, token)); if (action !== "delete") await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Operația nu a putut fi finalizată."); }
    finally { setBusy(false); }
  };

  if (!ready || (busy && !document)) return <LoadingState label="Încărcăm documentul și istoricul…" />;
  if (error && !document) return <ErrorState message={error} retry={() => void load()} />;
  if (!document) return <EmptyState title="Document indisponibil" description="Documentul nu există sau nu este accesibil în tenantul curent." icon={<Archive size={25} />} />;
  const canManage = user?.permissions.includes("documents.manage");
  const canDelete = user?.permissions.includes("documents.delete");
  return <>
    <PageHeader eyebrow="GovDocuments" title={document.original_filename} description={`Versiunea ${document.current_version_number} · ${document.classification}`} actions={<><Link className="button secondary" href="/legal/documents">Înapoi la registru</Link>{canManage && !document.archived_at ? <button className="button secondary" disabled={busy} onClick={() => void lifecycle("archive")}>Arhivează</button> : null}{canDelete && !document.deleted_at ? <button className="button danger-ghost" disabled={busy} onClick={() => void lifecycle("delete")}>Șterge</button> : null}{canDelete && document.deleted_at ? <button className="button primary" disabled={busy} onClick={() => void lifecycle("restore")}>Restaurează</button> : null}</>} />
    {error ? <ErrorState message={error} retry={() => void load()} /> : null}
    <section className="detail-grid"><article className="detail-card"><h2>Control document</h2><dl><div><dt>Stare</dt><dd><StatusBadge status={document.state} /></dd></div><div><dt>Categorie</dt><dd>{document.category}</dd></div><div><dt>Retenție</dt><dd>{formatDate(document.retention_until)}</dd></div><div><dt>ETag intern</dt><dd className="mono">{document.lock_version}</dd></div></dl></article><article className="detail-card"><h2>Asocieri</h2>{document.links.length ? <ul className="detail-list">{document.links.map((link) => <li key={link.id}><div><strong>{link.resource_type}</strong><p className="mono">{link.resource_id}</p></div></li>)}</ul> : <p className="muted">Document fără asociere.</p>}</article><article className="detail-card span-two"><h2>Versiuni</h2><ul className="detail-list">{versions.map((version) => <li key={version.id}><span className="item-icon"><Archive size={17} /></span><div><strong>v{version.version_number} · {version.original_filename}</strong><p>{Math.ceil(version.size_bytes / 1024)} KB · {formatDate(version.created_at)} · SHA-256 {version.checksum_sha256.slice(0, 16)}…</p><StatusBadge status={version.state} /> <button className="inline-action" disabled={busy || version.state !== "AVAILABLE"} onClick={() => void download(version)}>Descarcă versiunea</button></div></li>)}</ul>{canManage ? <form className="document-upload" onSubmit={addVersion}><label>Versiune nouă<input accept=".pdf,.txt,.csv,.docx,.xlsx,.png,.jpg,.jpeg" name="file" required type="file" /></label><button className="button secondary" disabled={busy}>{busy ? "Se procesează…" : "Încarcă versiune"}</button></form> : null}</article><article className="detail-card span-two"><h2>Istoric document</h2>{audit.length ? <ul className="detail-list">{audit.map((event) => <li key={event.id}><div><strong>{event.action.replaceAll("_", " ")}</strong><p>{formatDate(event.created_at)} · Request {event.request_id?.slice(0, 8) ?? "migrare"}</p></div></li>)}</ul> : <p className="muted">Nu există evenimente de audit.</p>}</article></section>
  </>;
}
