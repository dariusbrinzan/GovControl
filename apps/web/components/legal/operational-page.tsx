"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  apiDownload, apiGet, apiPatch, type CourtDecision, type DocumentRecord, type EnforcementProceeding,
  type LegalCase, type LegalObligation, type Notification, type PenaltyRule,
} from "../../lib/api";
import { downloadCsv, dueDateHint, dueInDays, formatDate, isOverdue, obligationTypeLabels } from "../../lib/legal";
import { Archive, Bell, BookOpenCheck, BriefcaseBusiness, CalendarClock, CircleDollarSign, FileCheck2, Files, Gavel } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { StatusBadge } from "../ui/status-badge";
import { useSession } from "./session-provider";
import { canCreate, CreateRecordDialog } from "./create-record-dialog";

export type OperationalView = "my-work" | "cases" | "decisions" | "obligations" | "deadlines" | "enforcements" | "penalties" | "documents" | "notifications";

type Resource = LegalCase | CourtDecision | LegalObligation | EnforcementProceeding | PenaltyRule | DocumentRecord | Notification;

const config: Record<OperationalView, { title: string; eyebrow: string; description: string; endpoint: string; icon: typeof Gavel }> = {
  "my-work": { title: "Activitatea mea", eyebrow: "Spațiu personal de lucru", description: "Obligațiile repartizate ție, ordonate după urgență și termen.", endpoint: "/legal/obligations", icon: BookOpenCheck },
  cases: { title: "Dosare juridice", eyebrow: "Management litigii", description: "Evidența centralizată a dosarelor și a stadiului lor procedural.", endpoint: "/legal/cases", icon: BriefcaseBusiness },
  decisions: { title: "Hotărâri judecătorești", eyebrow: "Acte jurisdicționale", description: "Hotărârile asociate dosarelor și datele relevante pentru executare.", endpoint: "/legal/decisions", icon: Gavel },
  obligations: { title: "Obligații instituționale", eyebrow: "Monitorizare executare", description: "Termene, responsabili și progres pentru fiecare obligație juridică.", endpoint: "/legal/obligations", icon: BookOpenCheck },
  deadlines: { title: "Termene critice", eyebrow: "Priorități operaționale", description: "Restanțe și scadențe apropiate care necesită acțiune imediată.", endpoint: "/legal/obligations", icon: CalendarClock },
  enforcements: { title: "Proceduri de executare", eyebrow: "Executare silită", description: "Procedurile deschise pentru obligații și stadiul lor curent.", endpoint: "/legal/enforcements", icon: FileCheck2 },
  penalties: { title: "Reguli și expunere", eyebrow: "Risc financiar", description: "Regulile de penalizare care contribuie la expunerea financiară estimată.", endpoint: "/legal/penalties/rules", icon: CircleDollarSign },
  documents: { title: "Registrul documentelor", eyebrow: "Evidență documentară", description: "Documente justificative încărcate pentru entitățile juridice.", endpoint: "/documents", icon: Files },
  notifications: { title: "Centrul de notificări", eyebrow: "Alerte și informări", description: "Alertele operaționale legate de termene și activitatea juridică.", endpoint: "/notifications", icon: Bell },
};

const obligationTransitions: Record<string, string[]> = {
  DRAFT: ["OPEN", "CANCELLED"], OPEN: ["IN_PROGRESS", "AT_RISK", "OVERDUE", "CANCELLED"],
  IN_PROGRESS: ["AT_RISK", "OVERDUE", "COMPLETED", "CANCELLED"],
  AT_RISK: ["IN_PROGRESS", "OVERDUE", "COMPLETED", "CANCELLED"],
  OVERDUE: ["IN_PROGRESS", "COMPLETED", "CANCELLED"], COMPLETED: [], CANCELLED: [],
};

export default function OperationalPage({ view }: { view: OperationalView }) {
  const page = config[view];
  const { token, user, ready } = useSession();
  const [items, setItems] = useState<Resource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [updating, setUpdating] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true); setError(null);
    try { setItems(await apiGet<Resource[]>(page.endpoint, token)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Datele nu au putut fi încărcate."); }
    finally { setLoading(false); }
  }, [page.endpoint, token]);
  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => items.filter((item) => {
    if (view === "my-work") {
      const obligation = item as LegalObligation;
      if (obligation.responsible_user_id !== user?.id) return false;
    }
    if (view === "deadlines") {
      const days = dueInDays((item as LegalObligation).due_date);
      if (days === null || days > 30 || ["COMPLETED", "CANCELLED"].includes((item as LegalObligation).status)) return false;
    }
    const text = JSON.stringify(item).toLocaleLowerCase("ro");
    if (query && !text.includes(query.toLocaleLowerCase("ro"))) return false;
    if (status && "status" in item && item.status !== status) return false;
    return true;
  }).sort((first, second) => {
    if ((view === "obligations" || view === "my-work" || view === "deadlines") && "due_date" in first && "due_date" in second) return (dueInDays(first.due_date) ?? 99999) - (dueInDays(second.due_date) ?? 99999);
    return 0;
  }), [items, query, status, user, view]);

  const exportRows = () => downloadCsv(`govlegal-${view}.csv`, [["Tip", "Identificator", "Date"], ...filtered.map((item) => [view, item.id, JSON.stringify(item)])]);
  const markRead = async (id: string) => {
    setUpdating(id);
    try { await apiPatch(`/notifications/${id}/read`, token, {}); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Notificarea nu a putut fi actualizată."); }
    finally { setUpdating(null); }
  };
  const changeStatus = async (id: string, nextStatus: string) => {
    setUpdating(id); setError(null);
    try {
      const endpoint = view === "enforcements" ? `/legal/enforcements/${id}/status` : `/legal/obligations/${id}/status`;
      await apiPatch(endpoint, token, { status: nextStatus }); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Statusul nu a putut fi actualizat."); }
    finally { setUpdating(null); }
  };
  const downloadDocument = async (document: DocumentRecord) => {
    setDownloading(document.id); setError(null);
    try {
      const content = await apiDownload(`/documents/${document.id}/download`, token);
      const url = URL.createObjectURL(content); const anchor = window.document.createElement("a");
      anchor.href = url; anchor.download = document.original_filename; anchor.click(); URL.revokeObjectURL(url);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Documentul nu a putut fi descărcat."); }
    finally { setDownloading(null); }
  };
  const Icon = page.icon;

  return <>
    <PageHeader eyebrow={page.eyebrow} title={page.title} description={page.description} actions={<><button className="button secondary" disabled={!filtered.length} onClick={exportRows}>Exportă CSV</button>{canCreate(view) && token ? <CreateRecordDialog view={view} token={token} onCreated={load} /> : null}</>} />
    <section className="list-toolbar" aria-label="Filtre listă"><label className="search-field"><span className="sr-only">Caută în listă</span><input onChange={(event) => setQuery(event.target.value)} placeholder="Filtrează rezultatele…" value={query} /></label>{!["decisions", "penalties", "documents"].includes(view) ? <label><span className="sr-only">Filtrează după status</span><select onChange={(event) => setStatus(event.target.value)} value={status}><option value="">Toate statusurile</option><option value="OPEN">Deschise</option><option value="IN_PROGRESS">În lucru</option><option value="AT_RISK">La risc</option><option value="OVERDUE">Depășite</option><option value="COMPLETED">Finalizate</option><option value="CLOSED">Închise</option><option value="UNREAD">Necitite</option></select></label> : null}<span className="result-count">{filtered.length} rezultate</span></section>
    {!ready || loading ? <LoadingState /> : null}{error ? <ErrorState message={error} retry={() => void load()} /> : null}
    {ready && user && !loading && !error && !filtered.length ? <EmptyState title={items.length ? "Niciun rezultat pentru filtrele alese" : "Nu există încă înregistrări"} description={items.length ? "Modifică termenii de căutare sau elimină filtrele." : "Înregistrările vor apărea aici după ce sunt adăugate în fluxul juridic."} icon={<Icon size={26} />} /> : null}
    {filtered.length ? <section className="data-panel"><div className="table-wrap"><table className="resource-table"><thead>{renderHeader(view)}</thead><tbody>{filtered.map((item) => renderRow(view, item, updating, markRead, changeStatus, downloading, downloadDocument))}</tbody></table></div></section> : null}
    {view === "my-work" && user && items.length > 0 && !filtered.length ? <p className="context-note">Nu ai obligații repartizate direct. Obligațiile fără responsabil individual rămân vizibile în pagina generală.</p> : null}
  </>;
}

function renderHeader(view: OperationalView) {
  if (["obligations", "my-work", "deadlines"].includes(view)) return <tr><th>Obligație</th><th>Tip</th><th>Termen</th><th>Status</th></tr>;
  if (view === "cases") return <tr><th>Dosar</th><th>Instanță</th><th>Obiect</th><th>Status</th></tr>;
  if (view === "decisions") return <tr><th>Hotărâre</th><th>Tip</th><th>Data</th><th>Dosar asociat</th></tr>;
  if (view === "enforcements") return <tr><th>Dosar executare</th><th>Executor / responsabil</th><th>Început</th><th>Status</th></tr>;
  if (view === "penalties") return <tr><th>Metodă</th><th>Parametri</th><th>Perioadă</th><th>Obligație</th></tr>;
  if (view === "documents") return <tr><th>Document</th><th>Categorie</th><th>Entitate</th><th>Încărcat</th></tr>;
  return <tr><th>Notificare</th><th>Termen</th><th>Status</th><th>Acțiune</th></tr>;
}

function renderRow(view: OperationalView, resource: Resource, updating: string | null, markRead: (id: string) => Promise<void>, changeStatus: (id: string, status: string) => Promise<void>, downloading: string | null, downloadDocument: (document: DocumentRecord) => Promise<void>) {
  if (["obligations", "my-work", "deadlines"].includes(view)) { const item = resource as LegalObligation; const transitions = obligationTransitions[item.status] ?? []; return <tr className={isOverdue(item) ? "urgent-row" : ""} key={item.id}><td><Link className="primary-cell" href={`/legal/obligations/${item.id}`}>{item.description}</Link><small>ID {item.id.slice(0, 8)}</small></td><td>{obligationTypeLabels[item.obligation_type] ?? item.obligation_type}</td><td><strong className={isOverdue(item) ? "text-danger" : ""}>{formatDate(item.due_date)}</strong><small>{dueDateHint(item)}</small></td><td><StatusBadge status={item.status} />{transitions.length ? <select aria-label={`Actualizează statusul pentru ${item.description}`} className="inline-status-select" defaultValue="" disabled={updating === item.id} onChange={(event) => { if (event.target.value) void changeStatus(item.id, event.target.value); }}><option value="">Actualizează…</option>{transitions.map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select> : null}</td></tr>; }
  if (view === "cases") { const item = resource as LegalCase; return <tr key={item.id}><td><Link className="primary-cell" href={`/legal/cases/${item.id}`}>{item.case_number}</Link><small>{formatDate(item.filing_date)}</small></td><td>{item.court}</td><td className="truncate-cell">{item.subject}</td><td><StatusBadge status={item.status} /></td></tr>; }
  if (view === "decisions") { const item = resource as CourtDecision; return <tr key={item.id}><td><strong>{item.decision_number}</strong></td><td>{item.decision_type}</td><td>{formatDate(item.decision_date)}</td><td><Link href={`/legal/cases/${item.case_id}`}>Vezi dosarul</Link></td></tr>; }
  if (view === "enforcements") { const item = resource as EnforcementProceeding; return <tr key={item.id}><td><strong>{item.file_number}</strong></td><td>{item.enforcement_officer ?? "Nerepartizat"}</td><td>{formatDate(item.start_date)}</td><td><StatusBadge status={item.status} /><select aria-label={`Actualizează statusul executării ${item.file_number}`} className="inline-status-select" disabled={updating === item.id} onChange={(event) => void changeStatus(item.id, event.target.value)} value={item.status}><option value="OPEN">OPEN</option><option value="SUSPENDED">SUSPENDED</option><option value="CLOSED">CLOSED</option></select></td></tr>; }
  if (view === "penalties") { const item = resource as PenaltyRule; return <tr key={item.id}><td><strong>{item.calculation_type === "DAILY_AMOUNT" ? "Sumă zilnică" : "Procent din bază"}</strong></td><td>{item.daily_amount ? `${item.daily_amount} RON/zi` : `${item.percentage}% din ${item.base_value} RON`}</td><td>{formatDate(item.start_date)} – {formatDate(item.end_date)}</td><td><Link href={`/legal/obligations/${item.obligation_id}`}>Vezi obligația</Link></td></tr>; }
  if (view === "documents") { const item = resource as DocumentRecord; return <tr key={item.id}><td><button className="document-download" disabled={downloading === item.id} onClick={() => void downloadDocument(item)}><strong>{downloading === item.id ? "Se descarcă…" : item.original_filename}</strong></button><small>{Math.ceil(item.size_bytes / 1024)} KB</small></td><td>{item.category.replaceAll("_", " ")}</td><td>{item.entity_type}</td><td>{formatDate(item.created_at)}</td></tr>; }
  const item = resource as Notification; return <tr className={item.status === "UNREAD" ? "unread-row" : ""} key={item.id}><td><strong>{item.title}</strong><small>{item.body}</small></td><td>{formatDate(item.due_date)}</td><td><StatusBadge status={item.status} /></td><td>{item.status === "UNREAD" ? <button className="table-action" disabled={updating === item.id} onClick={() => void markRead(item.id)}>Marchează citită</button> : "—"}</td></tr>;
}
