"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  apiDownload,
  apiGet,
  apiPatch,
  apiPost,
  apiUpload,
  type AuditEvent,
  type AuditEventPage,
  type CourtDecision,
  type DocumentRecord,
  type EnforcementProceeding,
  type LegalCase,
  type LegalDashboard,
  type LegalObligation,
  type LegalSearchResponse,
  type LegalSearchResult,
  type Notification,
  type PenaltyRule,
  type PenaltyExposure,
} from "../lib/api";

type WorkspaceData = {
  dashboard: LegalDashboard;
  obligations: LegalObligation[];
  cases: LegalCase[];
  decisions: CourtDecision[];
  enforcements: EnforcementProceeding[];
  penaltyRules: PenaltyRule[];
  auditEvents: AuditEvent[];
  notifications: Notification[];
};

type LegalWorkspaceProps = { view: "dashboard" | "obligations" };
type ObligationFilter = "all" | "attention" | "upcoming" | "completed";

const tokenStorageKey = "govcontrol.dev-token";

const allowedStatuses: Record<string, string[]> = {
  DRAFT: ["OPEN", "CANCELLED"],
  OPEN: ["IN_PROGRESS", "AT_RISK", "OVERDUE", "CANCELLED"],
  IN_PROGRESS: ["AT_RISK", "OVERDUE", "COMPLETED", "CANCELLED"],
  AT_RISK: ["IN_PROGRESS", "OVERDUE", "COMPLETED", "CANCELLED"],
  OVERDUE: ["IN_PROGRESS", "COMPLETED", "CANCELLED"],
  COMPLETED: [],
  CANCELLED: [],
};

const statusLabels: Record<string, string> = {
  DRAFT: "Ciornă",
  OPEN: "Deschisă",
  IN_PROGRESS: "În lucru",
  AT_RISK: "La risc",
  OVERDUE: "Depășit",
  COMPLETED: "Finalizată",
  CANCELLED: "Anulată",
  SUSPENDED: "Suspendată",
  CLOSED: "Închisă",
  DAILY_AMOUNT: "Sumă zilnică",
  PERCENTAGE_OF_BASE: "Procent din bază",
};

const obligationTypeLabels: Record<string, string> = {
  DO: "Executare",
  PAY: "Plată",
  REFRAIN: "Abținere",
  RESOLVE_REQUEST: "Soluționare cerere",
  ISSUE_DOCUMENT: "Emitere document",
  OTHER: "Alt tip",
};

function statusLabel(value: string): string {
  return statusLabels[value] ?? value.replaceAll("_", " ");
}

function obligationTypeLabel(value: string): string {
  return obligationTypeLabels[value] ?? value.replaceAll("_", " ");
}

function formatDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat("ro-RO").format(new Date(`${value}T00:00:00`)) : "—";
}

function isOverdue(obligation: LegalObligation): boolean {
  return Boolean(
    obligation.due_date &&
      obligation.status !== "COMPLETED" &&
      obligation.status !== "CANCELLED" &&
      new Date(`${obligation.due_date}T00:00:00`) < new Date(new Date().toDateString()),
  );
}

function dueInDays(value: string | null): number | null {
  if (!value) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const dueDate = new Date(`${value}T00:00:00`);
  return Math.round((dueDate.getTime() - today.getTime()) / 86_400_000);
}

function dueDateHint(obligation: LegalObligation): string {
  if (obligation.status === "COMPLETED") return "Finalizată";
  if (obligation.status === "CANCELLED") return "Anulată";
  const days = dueInDays(obligation.due_date);
  if (days === null) return "Fără termen stabilit";
  if (days < 0) return `Depășit cu ${Math.abs(days)} ${Math.abs(days) === 1 ? "zi" : "zile"}`;
  if (days === 0) return "Scadentă astăzi";
  if (days === 1) return "Scadentă mâine";
  return `Peste ${days} zile`;
}

function obligationPriority(obligation: LegalObligation): number {
  if (isOverdue(obligation) || obligation.status === "OVERDUE") return 0;
  if (obligation.status === "AT_RISK") return 1;
  const days = dueInDays(obligation.due_date);
  if (days !== null && days <= 7 && days >= 0) return 2;
  if (obligation.status === "COMPLETED" || obligation.status === "CANCELLED") return 4;
  return 3;
}

function formatFileSize(sizeBytes: number): string {
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1_048_576) return `${Math.round(sizeBytes / 1024)} KB`;
  return `${(sizeBytes / 1_048_576).toFixed(1)} MB`;
}

export default function LegalWorkspace({ view }: LegalWorkspaceProps) {
  const [token, setToken] = useState("");
  const [savedTokenToLoad, setSavedTokenToLoad] = useState<string | null>(null);
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [readingId, setReadingId] = useState<string | null>(null);
  const [creatingCase, setCreatingCase] = useState(false);
  const [creatingDecision, setCreatingDecision] = useState(false);
  const [creatingObligation, setCreatingObligation] = useState(false);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [documentsByObligation, setDocumentsByObligation] = useState<Record<string, DocumentRecord[]>>({});
  const [loadingDocumentsId, setLoadingDocumentsId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [creatingEnforcement, setCreatingEnforcement] = useState(false);
  const [updatingEnforcementId, setUpdatingEnforcementId] = useState<string | null>(null);
  const [exposures, setExposures] = useState<Record<string, string>>({});
  const [loadingExposureId, setLoadingExposureId] = useState<string | null>(null);
  const [creatingPenaltyRule, setCreatingPenaltyRule] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<LegalSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [obligationFilter, setObligationFilter] = useState<ObligationFilter>("all");

  useEffect(() => {
    const savedToken = window.localStorage.getItem(tokenStorageKey) ?? "";
    setToken(savedToken);
    setSavedTokenToLoad(savedToken || null);
  }, []);

  const loadWorkspace = useCallback(async () => {
    if (!token.trim()) {
      setError("Introdu tokenul DEV_AUTH_TOKEN din fișierul .env pentru a încărca datele.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [dashboard, obligations, cases, decisions, enforcements, penaltyRules, auditEvents, notifications] = await Promise.all([
        apiGet<LegalDashboard>("/legal/dashboard", token),
        apiGet<LegalObligation[]>("/legal/obligations", token),
        apiGet<LegalCase[]>("/legal/cases", token),
        apiGet<CourtDecision[]>("/legal/decisions", token),
        apiGet<EnforcementProceeding[]>("/legal/enforcements", token),
        apiGet<PenaltyRule[]>("/legal/penalties/rules", token),
        apiGet<AuditEventPage>("/audit/events", token),
        apiGet<Notification[]>("/notifications", token),
      ]);
      window.localStorage.setItem(tokenStorageKey, token);
      setData({
        dashboard,
        obligations,
        cases,
        decisions,
        enforcements,
        penaltyRules,
        auditEvents: auditEvents.items,
        notifications,
      });
    } catch (loadError) {
      setData(null);
      setError(loadError instanceof Error ? loadError.message : "Nu am putut încărca datele.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (savedTokenToLoad && token === savedTokenToLoad) {
      setSavedTokenToLoad(null);
      void loadWorkspace();
    }
  }, [loadWorkspace, savedTokenToLoad, token]);

  const changeStatus = async (obligationId: string, status: string) => {
    setUpdatingId(obligationId);
    setError(null);
    setSuccess(null);
    try {
      await apiPatch<LegalObligation>(`/legal/obligations/${obligationId}/status`, token, { status });
      await loadWorkspace();
      setSuccess("Statusul obligației a fost actualizat.");
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Statusul nu a putut fi actualizat.");
    } finally {
      setUpdatingId(null);
    }
  };

  const markNotificationRead = async (notificationId: string) => {
    setReadingId(notificationId);
    setError(null);
    setSuccess(null);
    try {
      await apiPatch<Notification>(`/notifications/${notificationId}/read`, token, {});
      await loadWorkspace();
      setSuccess("Notificarea a fost marcată ca citită.");
    } catch (readError) {
      setError(readError instanceof Error ? readError.message : "Notificarea nu a putut fi actualizată.");
    } finally {
      setReadingId(null);
    }
  };

  const createCase = async (form: HTMLFormElement) => {
    const values = new FormData(form);
    setCreatingCase(true);
    setError(null);
    setSuccess(null);
    try {
      await apiPost<LegalCase>("/legal/cases", token, {
        case_number: values.get("case_number"),
        court: values.get("court"),
        subject: values.get("subject"),
        filing_date: values.get("filing_date") || null,
      });
      form.reset();
      await loadWorkspace();
      setSuccess("Dosarul a fost înregistrat.");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Dosarul nu a putut fi creat.");
    } finally {
      setCreatingCase(false);
    }
  };

  const createDecision = async (form: HTMLFormElement) => {
    const values = new FormData(form);
    const caseId = String(values.get("case_id") ?? "");
    setCreatingDecision(true);
    setError(null);
    setSuccess(null);
    try {
      await apiPost(`/legal/cases/${caseId}/decisions`, token, {
        decision_number: values.get("decision_number"),
        decision_date: values.get("decision_date"),
        final_date: values.get("final_date") || null,
        decision_type: values.get("decision_type"),
        summary: values.get("summary") || null,
      });
      form.reset();
      await loadWorkspace();
      setSuccess("Hotărârea a fost înregistrată.");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Hotărârea nu a putut fi creată.");
    } finally {
      setCreatingDecision(false);
    }
  };

  const createObligation = async (form: HTMLFormElement) => {
    const values = new FormData(form);
    setCreatingObligation(true);
    setError(null);
    setSuccess(null);
    try {
      await apiPost<LegalObligation>("/legal/obligations", token, {
        court_decision_id: values.get("court_decision_id"),
        obligation_type: values.get("obligation_type"),
        description: values.get("description"),
        due_date: values.get("due_date") || null,
      });
      form.reset();
      await loadWorkspace();
      setSuccess("Obligația a fost adăugată și va fi urmărită automat.");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Obligația nu a putut fi creată.");
    } finally {
      setCreatingObligation(false);
    }
  };

  const uploadDocument = async (obligationId: string, file: File | undefined) => {
    if (!file) return;
    setUploadingId(obligationId);
    setError(null);
    setSuccess(null);
    const body = new FormData();
    body.set("entity_type", "LegalObligation");
    body.set("entity_id", obligationId);
    body.set("category", "SUPPORTING_DOCUMENT");
    body.set("file", file);
    try {
      const uploadedDocument = await apiUpload<DocumentRecord>("/documents", token, body);
      setDocumentsByObligation((current) => ({
        ...current,
        [obligationId]: [uploadedDocument, ...(current[obligationId] ?? [])],
      }));
      await loadWorkspace();
      setSuccess("Documentul justificativ a fost încărcat.");
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Documentul nu a putut fi încărcat.");
    } finally {
      setUploadingId(null);
    }
  };

  const loadDocuments = async (obligationId: string) => {
    if (documentsByObligation[obligationId]) return;
    setLoadingDocumentsId(obligationId);
    setError(null);
    try {
      const documents = await apiGet<DocumentRecord[]>(`/documents?entity_type=LegalObligation&entity_id=${obligationId}`, token);
      setDocumentsByObligation((current) => ({ ...current, [obligationId]: documents }));
    } catch (documentsError) {
      setError(documentsError instanceof Error ? documentsError.message : "Documentele nu au putut fi încărcate.");
    } finally {
      setLoadingDocumentsId(null);
    }
  };

  const downloadDocument = async (document: DocumentRecord) => {
    setDownloadingId(document.id);
    setError(null);
    setSuccess(null);
    try {
      const content = await apiDownload(`/documents/${document.id}/download`, token);
      const url = window.URL.createObjectURL(content);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = document.original_filename;
      window.document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setSuccess(`Documentul „${document.original_filename}” a fost descărcat.`);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "Documentul nu a putut fi descărcat.");
    } finally {
      setDownloadingId(null);
    }
  };

  const createEnforcement = async (form: HTMLFormElement) => {
    const values = new FormData(form);
    setCreatingEnforcement(true);
    setError(null);
    setSuccess(null);
    try {
      await apiPost<EnforcementProceeding>("/legal/enforcements", token, {
        obligation_id: values.get("obligation_id"),
        file_number: values.get("file_number"),
        enforcement_officer: values.get("enforcement_officer") || null,
        start_date: values.get("start_date"),
      });
      form.reset();
      await loadWorkspace();
      setSuccess("Procedura de executare a fost deschisă.");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Procedura nu a putut fi creată.");
    } finally {
      setCreatingEnforcement(false);
    }
  };

  const changeEnforcementStatus = async (enforcementId: string, status: string) => {
    setUpdatingEnforcementId(enforcementId);
    setError(null);
    setSuccess(null);
    try {
      await apiPatch<EnforcementProceeding>(`/legal/enforcements/${enforcementId}/status`, token, { status });
      await loadWorkspace();
      setSuccess("Statusul procedurii de executare a fost actualizat.");
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Executarea nu a putut fi actualizată.");
    } finally {
      setUpdatingEnforcementId(null);
    }
  };

  const loadExposure = async (ruleId: string) => {
    setLoadingExposureId(ruleId);
    setError(null);
    setSuccess(null);
    try {
      const exposure = await apiGet<PenaltyExposure>(`/legal/penalties/rules/${ruleId}/exposure`, token);
      setExposures((current) => ({ ...current, [ruleId]: exposure.amount }));
      setSuccess("Expunerea la penalități a fost calculată la zi.");
    } catch (exposureError) {
      setError(exposureError instanceof Error ? exposureError.message : "Expunerea nu a putut fi calculată.");
    } finally {
      setLoadingExposureId(null);
    }
  };

  const createPenaltyRule = async (form: HTMLFormElement) => {
    const values = new FormData(form);
    setCreatingPenaltyRule(true);
    setError(null);
    setSuccess(null);
    try {
      await apiPost<PenaltyRule>("/legal/penalties/rules", token, {
        obligation_id: values.get("obligation_id"),
        calculation_type: values.get("calculation_type"),
        daily_amount: values.get("daily_amount") || null,
        percentage: values.get("percentage") || null,
        base_value: values.get("base_value") || null,
        start_date: values.get("start_date"),
        end_date: values.get("end_date") || null,
      });
      form.reset();
      await loadWorkspace();
      setSuccess("Regula de penalizare a fost salvată.");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Regula de penalizare nu a putut fi creată.");
    } finally {
      setCreatingPenaltyRule(false);
    }
  };

  const searchLegal = async () => {
    const query = searchQuery.trim();
    if (!token.trim()) {
      setError("Conectează aplicația înainte de a căuta în datele instituției.");
      return;
    }
    if (query.length < 2) {
      setError("Introdu cel puțin două caractere pentru căutare.");
      return;
    }
    setSearching(true);
    setError(null);
    setSuccess(null);
    setSearchResults([]);
    setHasSearched(false);
    try {
      const response = await apiGet<LegalSearchResponse>(`/search/legal?q=${encodeURIComponent(query)}`, token);
      setSearchResults(response.results);
      setHasSearched(true);
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : "Căutarea nu a putut fi executată.");
    } finally {
      setSearching(false);
    }
  };

  const prioritizedObligations = [...(data?.obligations ?? [])].sort((first, second) => {
    const priorityDifference = obligationPriority(first) - obligationPriority(second);
    if (priorityDifference !== 0) return priorityDifference;
    return (dueInDays(first.due_date) ?? Number.MAX_SAFE_INTEGER) - (dueInDays(second.due_date) ?? Number.MAX_SAFE_INTEGER);
  });
  const filteredObligations = prioritizedObligations.filter((item) => {
    if (obligationFilter === "attention") return isOverdue(item) || item.status === "OVERDUE" || item.status === "AT_RISK";
    if (obligationFilter === "upcoming") {
      const days = dueInDays(item.due_date);
      return days !== null && days >= 0 && days <= 7 && item.status !== "COMPLETED" && item.status !== "CANCELLED";
    }
    if (obligationFilter === "completed") return item.status === "COMPLETED" || item.status === "CANCELLED";
    return true;
  });
  const shownObligations = view === "obligations" ? filteredObligations : prioritizedObligations.slice(0, 5);

  return (
    <main className="app-shell">
      <a className="skip-link" href="#main-content">Sari la conținut</a>
      <header className="topbar">
        <Link className="brand" href="/">GovControl</Link>
        <nav aria-label="Navigare principală">
          <Link className={view === "dashboard" ? "active" : ""} href="/legal">Panou GovLegal</Link>
          <Link className={view === "obligations" ? "active" : ""} href="/legal/obligations">Obligații</Link>
        </nav>
      </header>

      <section className="page-heading" id="main-content" tabIndex={-1}>
        <p className="eyebrow">GovLegal · mediu local</p>
        <h1>{view === "dashboard" ? "Control operațional" : "Obligații și termene"}</h1>
        <p>{view === "dashboard" ? "Vezi ce necesită atenție, apoi intră direct în acțiunea potrivită." : "Urmărește termenele, actualizează progresul și păstrează dovezile într-un singur loc."}</p>
      </section>

      <section className="connection-card" aria-label="Conectare API local">
        <details open={!token.trim()}>
          <summary><span>Conexiune la date</span><strong>{data ? "Date încărcate" : "Conectează aplicația"}</strong></summary>
          <div className="connection-content">
            <label htmlFor="dev-token">Token local de dezvoltare</label>
            <div className="token-row">
              <input
                id="dev-token"
                value={token}
                onChange={(event) => setToken(event.target.value)}
                placeholder="DEV_AUTH_TOKEN din .env"
                type="password"
                autoComplete="off"
              />
              <button onClick={() => void loadWorkspace()} disabled={loading} type="button">
                {loading ? "Se încarcă…" : data ? "Reîncarcă datele" : "Încarcă datele"}
              </button>
            </div>
            <p>Tokenul este păstrat numai în localStorage-ul acestui browser local.</p>
          </div>
        </details>
      </section>

      {error ? <p className="notice error" role="alert">{error}</p> : null}
      {success ? <p className="notice success" role="status">{success}</p> : null}

      <section className="search-card">
        <form onSubmit={(event) => { event.preventDefault(); void searchLegal(); }}>
          <label htmlFor="legal-search">Găsește rapid un dosar sau o obligație</label><div><input id="legal-search" minLength={2} onChange={(event) => { setSearchQuery(event.target.value); if (!event.target.value.trim()) { setSearchResults([]); setHasSearched(false); } }} placeholder="Ex.: 1234/2026 sau cuvinte din obligație" value={searchQuery} /><button disabled={searching} type="submit">{searching ? "Se caută…" : "Caută"}</button></div>
        </form>
        {searching ? <p className="search-feedback" role="status">Căutăm în dosare și obligații…</p> : null}
        {!searching && searchResults.length ? <ul aria-label="Rezultate căutare">{searchResults.map((item) => <li key={`${item.entity_type}-${item.id}`}><strong>{item.title}</strong><span>{item.entity_type === "LegalCase" ? "Dosar" : "Obligație"} · {statusLabel(item.status)}</span><p>{item.summary}</p></li>)}</ul> : null}
        {hasSearched && !searching && !searchResults.length ? <p className="search-feedback">Nu am găsit rezultate. Încearcă numărul dosarului sau un cuvânt din descriere.</p> : null}
      </section>

      {data ? (
        <>
          <section className="metric-grid" aria-label="Indicatori obligații">
            <article><span>Obligații deschise</span><strong>{data.dashboard.open_obligations}</strong><small>de urmărit acum</small></article>
            <article className={data.dashboard.overdue_obligations ? "danger" : ""}><span>Termene depășite</span><strong>{data.dashboard.overdue_obligations}</strong><small>{data.dashboard.overdue_obligations ? "intervenție necesară" : "fără restanțe"}</small></article>
            <article><span>Scadente curând</span><strong>{data.dashboard.due_within_seven_days}</strong><small>în următoarele 7 zile</small></article>
            <article><span>Zile întârziere</span><strong>{data.dashboard.overdue_days_total}</strong><small>cumulate în toate obligațiile</small></article>
          </section>

          {view === "obligations" ? <section className="filter-bar" aria-label="Filtrează obligațiile">
            <div><strong>Arată-mi</strong><span>Obligațiile sunt ordonate automat după urgență.</span></div>
            <div className="filter-options" role="group" aria-label="Selectare filtru">
              <button aria-pressed={obligationFilter === "all"} className={obligationFilter === "all" ? "selected" : ""} onClick={() => setObligationFilter("all")} type="button">Toate</button>
              <button aria-pressed={obligationFilter === "attention"} className={obligationFilter === "attention" ? "selected" : ""} onClick={() => setObligationFilter("attention")} type="button">Necesită atenție</button>
              <button aria-pressed={obligationFilter === "upcoming"} className={obligationFilter === "upcoming" ? "selected" : ""} onClick={() => setObligationFilter("upcoming")} type="button">În următoarele 7 zile</button>
              <button aria-pressed={obligationFilter === "completed"} className={obligationFilter === "completed" ? "selected" : ""} onClick={() => setObligationFilter("completed")} type="button">Finalizate</button>
            </div>
          </section> : null}

          <section className="content-grid">
            <article className="panel obligations-panel">
              <div className="panel-heading">
                <div><h2>{view === "obligations" ? "Obligații" : "Obligații prioritare"}</h2><p aria-live="polite">{shownObligations.length} {shownObligations.length === 1 ? "înregistrare afișată" : "înregistrări afișate"}</p></div>
                {view === "dashboard" ? <Link href="/legal/obligations">Vezi toate</Link> : null}
              </div>
              {shownObligations.length ? (
                <div className="table-wrap"><table><thead><tr><th>Obligație</th><th>Termen</th><th>Status</th><th>Documente</th></tr></thead><tbody>
                  {shownObligations.map((item) => <tr key={item.id}><td><strong>{item.description}</strong><small>{obligationTypeLabel(item.obligation_type)}</small></td><td className={isOverdue(item) ? "text-danger" : ""}>{formatDate(item.due_date)}<small className={isOverdue(item) ? "text-danger" : ""}>{dueDateHint(item)}</small></td><td><span className={`status status-${item.status.toLowerCase()}`}>{statusLabel(item.status)}</span>{allowedStatuses[item.status].length ? <select aria-label={`Schimbă statusul obligației ${item.description}`} className="status-select" defaultValue="" disabled={updatingId === item.id} onChange={(event) => { if (event.target.value) void changeStatus(item.id, event.target.value); }}><option value="">Schimbă statusul</option>{allowedStatuses[item.status].map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}</select> : null}</td><td><details className="document-menu" onToggle={(event) => { if (event.currentTarget.open) void loadDocuments(item.id); }}><summary>Gestionează documente</summary><div className="document-menu-content"><label className="upload-control">{uploadingId === item.id ? "Se încarcă…" : "Adaugă dovadă"}<input aria-label={`Adaugă document justificativ pentru ${item.description}`} disabled={uploadingId === item.id} onChange={(event) => void uploadDocument(item.id, event.target.files?.[0])} type="file" /></label>{loadingDocumentsId === item.id ? <p>Se încarcă documentele…</p> : documentsByObligation[item.id]?.length ? <ul>{documentsByObligation[item.id].map((document) => <li key={document.id}><button disabled={downloadingId === document.id} onClick={() => void downloadDocument(document)} type="button">{downloadingId === document.id ? "Se descarcă…" : document.original_filename}</button><small>{formatFileSize(document.size_bytes)} · {formatDate(document.created_at.slice(0, 10))}</small></li>)}</ul> : <p>Nu există documente încă.</p>}</div></details></td></tr>)}
                </tbody></table></div>
              ) : <p className="empty-state">{view === "obligations" && obligationFilter !== "all" ? "Nu există obligații care corespund acestui filtru. Alege „Toate” pentru a reveni la listă." : "Nu există încă obligații înregistrate pentru acest tenant."}</p>}
            </article>

            {view === "dashboard" ? <aside className="side-column">
              <article className="panel"><h2>Dosare</h2><strong className="large-number">{data.cases.length}</strong><p>dosare accesibile în tenantul curent</p></article>
              <article className="panel"><h2>Executări</h2><strong className="large-number">{data.enforcements.length}</strong><p>proceduri active sau istorice</p></article>
              <article className="panel"><h2>Reguli de penalizare</h2><strong className="large-number">{data.penaltyRules.length}</strong><p>reguli disponibile pentru calculul expunerii</p></article>
              <article className="panel"><h2>Notificări</h2><strong className="large-number">{data.notifications.filter((item) => item.status === "UNREAD").length}</strong><p>alerte necitite privind termenele</p></article>
            </aside> : null}
          </section>

          {view === "dashboard" && data.enforcements.length ? <section className="panel create-case-panel"><div className="panel-heading"><div><h2>Proceduri de executare</h2><p>Actualizează ciclul de viață al fiecărei proceduri.</p></div></div><div className="table-wrap"><table><thead><tr><th>Număr dosar</th><th>Responsabil</th><th>Început</th><th>Status</th></tr></thead><tbody>{data.enforcements.map((item) => <tr key={item.id}><td><strong>{item.file_number}</strong></td><td>{item.enforcement_officer ?? "—"}</td><td>{formatDate(item.start_date)}</td><td><select aria-label={`Status executare ${item.file_number}`} className="status-select" disabled={updatingEnforcementId === item.id} onChange={(event) => void changeEnforcementStatus(item.id, event.target.value)} value={item.status}><option value="OPEN">Deschisă</option><option value="SUSPENDED">Suspendată</option><option value="CLOSED">Închisă</option></select></td></tr>)}</tbody></table></div></section> : null}

          {view === "dashboard" && data.penaltyRules.length ? <section className="panel create-case-panel"><div className="panel-heading"><div><h2>Expunere la penalități</h2><p>Calcul derivat la data curentă pentru fiecare regulă.</p></div></div><div className="table-wrap"><table><thead><tr><th>Metodă</th><th>Început</th><th>Expunere</th></tr></thead><tbody>{data.penaltyRules.map((item) => <tr key={item.id}><td>{statusLabel(item.calculation_type)}</td><td>{formatDate(item.start_date)}</td><td>{exposures[item.id] ? <strong>{exposures[item.id]}</strong> : <button className="inline-action" disabled={loadingExposureId === item.id} onClick={() => void loadExposure(item.id)} type="button">{loadingExposureId === item.id ? "Se calculează…" : "Calculează"}</button>}</td></tr>)}</tbody></table></div></section> : null}

          <section className="workflow-section" aria-labelledby="actions-heading">
            <div className="section-intro">
              <div><p className="eyebrow">Acțiuni administrative</p><h2 id="actions-heading">Înregistrează doar ce ai nevoie</h2></div>
              <p>Formularele sunt pliate pentru a păstra ecranul clar. Deschide o acțiune, completează câmpurile și salvează.</p>
            </div>
            <div className="workflow-grid">
              {view === "dashboard" ? <details className="workflow-card">
                <summary><span className="workflow-kicker">Pasul 1</span><strong>Înregistrează dosar</strong><small>Începe evidența unui litigiu sau demers juridic.</small></summary>
                <div className="workflow-body"><form className="case-form" onSubmit={(event) => { event.preventDefault(); void createCase(event.currentTarget); }}>
                  <label>Număr dosar<input name="case_number" required /></label>
                  <label>Instanță<input name="court" required /></label>
                  <label>Data înregistrării<input name="filing_date" type="date" /></label>
                  <label className="wide">Obiect<textarea name="subject" required rows={2} /></label>
                  <button disabled={creatingCase} type="submit">{creatingCase ? "Se creează…" : "Salvează dosarul"}</button>
                </form></div>
              </details> : null}

              {view === "dashboard" && data.cases.length ? <details className="workflow-card">
                <summary><span className="workflow-kicker">Pasul 2</span><strong>Înregistrează hotărâre</strong><small>Leagă hotărârea de dosarul relevant.</small></summary>
                <div className="workflow-body"><form className="case-form" onSubmit={(event) => { event.preventDefault(); void createDecision(event.currentTarget); }}>
                  <label>Dosar<select name="case_id" required><option value="">Alege dosarul…</option>{data.cases.map((item) => <option key={item.id} value={item.id}>{item.case_number} · {item.court}</option>)}</select></label>
                  <label>Număr hotărâre<input name="decision_number" required /></label>
                  <label>Data hotărârii<input name="decision_date" required type="date" /></label>
                  <label>Tip hotărâre<input name="decision_type" placeholder="Ex.: Sentință" required /></label>
                  <label>Data rămânerii definitive<input name="final_date" type="date" /></label>
                  <label className="wide">Rezumat<textarea name="summary" rows={2} /></label>
                  <button disabled={creatingDecision} type="submit">{creatingDecision ? "Se creează…" : "Salvează hotărârea"}</button>
                </form></div>
              </details> : null}

              {view === "obligations" && data.decisions.length ? <details className="workflow-card">
                <summary><span className="workflow-kicker">Acțiune principală</span><strong>Adaugă obligație</strong><small>Termenul va apărea în panou și în notificări.</small></summary>
                <div className="workflow-body"><form className="case-form" onSubmit={(event) => { event.preventDefault(); void createObligation(event.currentTarget); }}>
                  <label>Hotărâre<select name="court_decision_id" required><option value="">Alege hotărârea…</option>{data.decisions.map((item) => <option key={item.id} value={item.id}>{item.decision_number} · {item.decision_type}</option>)}</select></label>
                  <label>Tip obligație<select defaultValue="DO" name="obligation_type"><option value="DO">Executare</option><option value="PAY">Plată</option><option value="REFRAIN">Abținere</option><option value="RESOLVE_REQUEST">Soluționare cerere</option><option value="ISSUE_DOCUMENT">Emiterea documentului</option><option value="OTHER">Alt tip</option></select></label>
                  <label>Termen<input name="due_date" type="date" /></label>
                  <label className="wide">Descriere<textarea name="description" required rows={2} /></label>
                  <button disabled={creatingObligation} type="submit">{creatingObligation ? "Se creează…" : "Salvează obligația"}</button>
                </form></div>
              </details> : null}

              {view === "obligations" && data.obligations.length ? <details className="workflow-card">
                <summary><span className="workflow-kicker">Acțiune avansată</span><strong>Deschide executare</strong><small>Înregistrează o procedură pentru o obligație existentă.</small></summary>
                <div className="workflow-body"><form className="case-form" onSubmit={(event) => { event.preventDefault(); void createEnforcement(event.currentTarget); }}>
                  <label>Obligație<select name="obligation_id" required><option value="">Alege obligația…</option>{data.obligations.map((item) => <option key={item.id} value={item.id}>{item.description.slice(0, 70)}</option>)}</select></label>
                  <label>Număr dosar executare<input name="file_number" required /></label>
                  <label>Data deschiderii<input name="start_date" required type="date" /></label>
                  <label>Executor / responsabil<input name="enforcement_officer" /></label>
                  <button disabled={creatingEnforcement} type="submit">{creatingEnforcement ? "Se creează…" : "Salvează executarea"}</button>
                </form></div>
              </details> : null}

              {view === "obligations" && data.obligations.length ? <details className="workflow-card">
                <summary><span className="workflow-kicker">Acțiune avansată</span><strong>Adaugă regulă de penalizare</strong><small>Calculează expunerea fără a salva o sumă agregată.</small></summary>
                <div className="workflow-body"><form className="case-form" onSubmit={(event) => { event.preventDefault(); void createPenaltyRule(event.currentTarget); }}>
                  <label>Obligație<select name="obligation_id" required><option value="">Alege obligația…</option>{data.obligations.map((item) => <option key={item.id} value={item.id}>{item.description.slice(0, 70)}</option>)}</select></label>
                  <label>Metodă<select defaultValue="DAILY_AMOUNT" name="calculation_type"><option value="DAILY_AMOUNT">Sumă pe zi</option><option value="PERCENTAGE_OF_BASE">Procent din bază / zi</option></select></label>
                  <label>Data început<input name="start_date" required type="date" /></label>
                  <label>Sumă zilnică<input min="0" name="daily_amount" step="0.01" type="number" /></label>
                  <label>Procent zilnic<input min="0" name="percentage" step="0.0001" type="number" /></label>
                  <label>Valoare bază<input min="0" name="base_value" step="0.01" type="number" /></label>
                  <label>Data sfârșit<input name="end_date" type="date" /></label>
                  <button disabled={creatingPenaltyRule} type="submit">{creatingPenaltyRule ? "Se creează…" : "Salvează regula"}</button>
                </form></div>
              </details> : null}
            </div>
          </section>

          {view === "dashboard" ? <section className="panel audit-panel"><div className="panel-heading"><div><h2>Activitate recentă</h2><p>Jurnalul de audit al tenantului</p></div></div>
            {data.auditEvents.length ? <ul className="audit-list">{data.auditEvents.slice(0, 6).map((event) => <li key={event.id}><strong>{event.action}</strong><span>{event.entity_type}</span><time>{new Intl.DateTimeFormat("ro-RO", { dateStyle: "medium", timeStyle: "short" }).format(new Date(event.created_at))}</time></li>)}</ul> : <p className="empty-state">Nu există evenimente de audit încă.</p>}
          </section> : null}
          {view === "dashboard" ? <section className="panel notifications-panel"><div className="panel-heading"><div><h2>Notificări</h2><p>Alerte de termen pentru utilizatorul curent</p></div></div>
            {data.notifications.length ? <ul className="notification-list">{data.notifications.slice(0, 6).map((item) => <li className={item.status === "UNREAD" ? "unread" : ""} key={item.id}><div><strong>{item.title}</strong><p>{item.body}</p></div>{item.status === "UNREAD" ? <button disabled={readingId === item.id} onClick={() => void markNotificationRead(item.id)} type="button">{readingId === item.id ? "Se salvează…" : "Marchează citită"}</button> : <span>Citită</span>}</li>)}</ul> : <p className="empty-state">Nu există notificări pentru utilizatorul curent.</p>}
          </section> : null}
        </>
      ) : loading ? <section className="loading-state" role="status" aria-live="polite"><span aria-hidden="true" /><div><strong>Se încarcă spațiul de lucru</strong><p>Pregătim dosarele, obligațiile și alertele relevante.</p></div></section> : !error ? <p className="notice">Introdu tokenul local pentru a vedea datele operaționale.</p> : null}
    </main>
  );
}
