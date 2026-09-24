"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { apiGet, type CourtDecision, type DocumentRecord, type LegalCase, type LegalObligation } from "../../lib/api";
import { dueDateHint, formatDate, obligationTypeLabels } from "../../lib/legal";
import { Archive, BriefcaseBusiness } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { StatusBadge } from "../ui/status-badge";
import { useSession } from "./session-provider";

export function EntityDetail({ entity, id }: { entity: "case" | "obligation"; id: string }) {
  const { token, ready } = useSession();
  const [item, setItem] = useState<LegalCase | LegalObligation | null>(null);
  const [related, setRelated] = useState<Array<CourtDecision | DocumentRecord>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true); setError(null);
    try {
      if (entity === "case") {
        const current = await apiGet<LegalCase>(`/legal/cases/${id}`, token);
        const decisions = await apiGet<CourtDecision[]>(`/legal/decisions?case_id=${id}`, token);
        setItem(current); setRelated(decisions);
      } else {
        const current = await apiGet<LegalObligation>(`/legal/obligations/${id}`, token);
        const documents = await apiGet<DocumentRecord[]>(`/documents?entity_type=LegalObligation&entity_id=${id}`, token);
        setItem(current); setRelated(documents);
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
    return <><PageHeader eyebrow="Fișă dosar" title={current.case_number} description={current.subject} actions={<Link className="button secondary" href="/legal/cases">Înapoi la dosare</Link>} /><section className="detail-grid"><article className="detail-card"><h2>Date generale</h2><dl><div><dt>Instanță</dt><dd>{current.court}</dd></div><div><dt>Data înregistrării</dt><dd>{formatDate(current.filing_date)}</dd></div><div><dt>Status</dt><dd><StatusBadge status={current.status} /></dd></div><div><dt>Identificator</dt><dd className="mono">{current.id}</dd></div></dl></article><article className="detail-card span-two"><h2>Hotărâri asociate</h2>{related.length ? <ul className="detail-list">{(related as CourtDecision[]).map((decision) => <li key={decision.id}><span className="item-icon"><BriefcaseBusiness size={17} /></span><div><strong>{decision.decision_number}</strong><p>{decision.decision_type} · {formatDate(decision.decision_date)}</p></div></li>)}</ul> : <p className="muted">Nu există hotărâri asociate.</p>}</article></section></>;
  }
  const current = item as LegalObligation;
  return <><PageHeader eyebrow="Fișă obligație" title="Detaliu obligație" description={current.description} actions={<Link className="button secondary" href="/legal/obligations">Înapoi la obligații</Link>} /><section className="detail-grid"><article className="detail-card"><h2>Stare curentă</h2><dl><div><dt>Status</dt><dd><StatusBadge status={current.status} /></dd></div><div><dt>Tip</dt><dd>{obligationTypeLabels[current.obligation_type] ?? current.obligation_type}</dd></div><div><dt>Termen</dt><dd>{formatDate(current.due_date)}<small>{dueDateHint(current)}</small></dd></div><div><dt>Data finalizării</dt><dd>{formatDate(current.completion_date)}</dd></div></dl></article><article className="detail-card"><h2>Responsabilitate</h2><dl><div><dt>Departament</dt><dd className="mono">{current.responsible_department_id ?? "Nerepartizat"}</dd></div><div><dt>Responsabil</dt><dd className="mono">{current.responsible_user_id ?? "Nerepartizat"}</dd></div><div><dt>Actualizat</dt><dd>{formatDate(current.updated_at)}</dd></div></dl></article><article className="detail-card span-two"><h2>Documente justificative</h2>{related.length ? <ul className="detail-list">{(related as DocumentRecord[]).map((document) => <li key={document.id}><span className="item-icon"><Archive size={17} /></span><div><strong>{document.original_filename}</strong><p>{document.category.replaceAll("_", " ")} · {Math.ceil(document.size_bytes / 1024)} KB</p></div></li>)}</ul> : <p className="muted">Nu există documente atașate.</p>}</article></section></>;
}
