"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { apiGet, type CourtDecision, type LegalCase, type LegalObligation } from "../../lib/api";
import {
  documentsDownload,
  documentsList,
  documentsUpload,
  type DocumentRecord,
} from "../../lib/documents";
import { dueDateHint, formatDate, obligationTypeLabels } from "../../lib/legal";
import { Archive, BriefcaseBusiness } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { StatusBadge } from "../ui/status-badge";
import { useSession } from "./session-provider";

export function EntityDetail({ entity, id }: { entity: "case" | "obligation"; id: string }) {
  const { token, ready } = useSession();
  const [item, setItem] = useState<LegalCase | LegalObligation | null>(null);
  const [decisions, setDecisions] = useState<CourtDecision[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true); setError(null);
    try {
      if (entity === "case") {
        const [current, relatedDecisions, relatedDocuments] = await Promise.all([
          apiGet<LegalCase>(`/legal/cases/${id}`, token),
          apiGet<CourtDecision[]>(`/legal/decisions?case_id=${id}`, token),
          documentsList(token, { resource_type: "LegalCase", resource_id: id }),
        ]);
        setItem(current); setDecisions(relatedDecisions); setDocuments(relatedDocuments.items);
      } else {
        const [current, relatedDocuments] = await Promise.all([
          apiGet<LegalObligation>(`/legal/obligations/${id}`, token),
          documentsList(token, { resource_type: "LegalObligation", resource_id: id }),
        ]);
        setItem(current); setDocuments(relatedDocuments.items);
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Detaliile nu au putut fi încărcate."); }
    finally { setLoading(false); }
  }, [entity, id, token]);
  useEffect(() => { void load(); }, [load]);
  if (!ready || loading) return <LoadingState label="Încărcăm fișa completă…" />;
  if (error) return <ErrorState message={error} retry={() => void load()} />;
  if (!item) return <EmptyState title="Fișa nu este disponibilă" description="Conectează aplicația sau revino la lista principală." icon={<Archive size={25} />} />;
  if (entity === "case") {
    const current = item as LegalCase;
    return <><PageHeader eyebrow="Fișă dosar" title={current.case_number} description={current.subject} actions={<Link className="button secondary" href="/legal/cases">Înapoi la dosare</Link>} /><section className="detail-grid"><article className="detail-card"><h2>Date generale</h2><dl><div><dt>Instanță</dt><dd>{current.court}</dd></div><div><dt>Data înregistrării</dt><dd>{formatDate(current.filing_date)}</dd></div><div><dt>Status</dt><dd><StatusBadge status={current.status} /></dd></div><div><dt>Identificator</dt><dd className="mono">{current.id}</dd></div></dl></article><article className="detail-card span-two"><h2>Hotărâri asociate</h2>{decisions.length ? <ul className="detail-list">{decisions.map((decision) => <li key={decision.id}><span className="item-icon"><BriefcaseBusiness size={17} /></span><div><strong>{decision.decision_number}</strong><p>{decision.decision_type} · {formatDate(decision.decision_date)}</p></div></li>)}</ul> : <p className="muted">Nu există hotărâri asociate.</p>}</article><DocumentList documents={documents} onChanged={load} resourceId={id} resourceType="LegalCase" token={token} /></section></>;
  }
  const current = item as LegalObligation;
  return <><PageHeader eyebrow="Fișă obligație" title="Detaliu obligație" description={current.description} actions={<Link className="button secondary" href="/legal/obligations">Înapoi la obligații</Link>} /><section className="detail-grid"><article className="detail-card"><h2>Stare curentă</h2><dl><div><dt>Status</dt><dd><StatusBadge status={current.status} /></dd></div><div><dt>Tip</dt><dd>{obligationTypeLabels[current.obligation_type] ?? current.obligation_type}</dd></div><div><dt>Termen</dt><dd>{formatDate(current.due_date)}<small>{dueDateHint(current)}</small></dd></div><div><dt>Data finalizării</dt><dd>{formatDate(current.completion_date)}</dd></div></dl></article><article className="detail-card"><h2>Responsabilitate</h2><dl><div><dt>Departament</dt><dd className="mono">{current.responsible_department_id ?? "Nerepartizat"}</dd></div><div><dt>Responsabil</dt><dd className="mono">{current.responsible_user_id ?? "Nerepartizat"}</dd></div><div><dt>Actualizat</dt><dd>{formatDate(current.updated_at)}</dd></div></dl></article><DocumentList documents={documents} onChanged={load} resourceId={id} resourceType="LegalObligation" token={token} /></section></>;
}

function DocumentList({ documents, onChanged, resourceId, resourceType, token }: { documents: DocumentRecord[]; onChanged: () => Promise<void>; resourceId: string; resourceType: "LegalCase" | "LegalObligation"; token: string }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const upload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    data.set("resource_type", resourceType); data.set("resource_id", resourceId); data.set("category", "SUPPORTING_DOCUMENT");
    setBusy(true); setError(null);
    try { await documentsUpload(token, data); form.reset(); await onChanged(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Documentul nu a putut fi încărcat."); }
    finally { setBusy(false); }
  };
  const download = async (document: DocumentRecord) => {
    setBusy(true); setError(null);
    try { const blob = await documentsDownload(document.id, token); const url = URL.createObjectURL(blob); const anchor = window.document.createElement("a"); anchor.href = url; anchor.download = document.original_filename; anchor.click(); URL.revokeObjectURL(url); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Documentul nu a putut fi descărcat."); }
    finally { setBusy(false); }
  };
  return <article className="detail-card span-two"><h2>Documente asociate</h2>{documents.length ? <ul className="detail-list">{documents.map((document) => <li key={document.id}><span className="item-icon"><Archive size={17} /></span><div><Link href={`/legal/documents/${document.id}`}><strong>{document.original_filename}</strong></Link><p>{document.category.replaceAll("_", " ")} · {Math.ceil(document.size_bytes / 1024)} KB · v{document.current_version_number}</p><button className="inline-action" disabled={busy || document.state !== "AVAILABLE"} onClick={() => void download(document)}>Descarcă</button></div></li>)}</ul> : <p className="muted">Nu există documente atașate.</p>}<form className="document-upload" onSubmit={upload}><label>Adaugă document<input accept=".pdf,.txt,.csv,.docx,.xlsx,.png,.jpg,.jpeg" name="file" required type="file" /></label><button className="button secondary" disabled={busy}>{busy ? "Se procesează…" : "Încarcă"}</button></form>{error ? <div className="inline-error" role="alert">{error}</div> : null}</article>;
}
