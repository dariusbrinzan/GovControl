"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  apiGet,
  apiPatch,
  apiPost,
  apiUpload,
  type AuditEvent,
  type AuditEventPage,
  type CourtDecision,
  type EnforcementProceeding,
  type LegalCase,
  type LegalDashboard,
  type LegalObligation,
  type LegalSearchResponse,
  type LegalSearchResult,
  type Notification,
  type PenaltyRule,
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

export default function LegalWorkspace({ view }: LegalWorkspaceProps) {
  const [token, setToken] = useState("");
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [readingId, setReadingId] = useState<string | null>(null);
  const [creatingCase, setCreatingCase] = useState(false);
  const [creatingDecision, setCreatingDecision] = useState(false);
  const [creatingObligation, setCreatingObligation] = useState(false);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [creatingEnforcement, setCreatingEnforcement] = useState(false);
  const [creatingPenaltyRule, setCreatingPenaltyRule] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<LegalSearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => setToken(window.localStorage.getItem(tokenStorageKey) ?? ""), []);

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

  const changeStatus = async (obligationId: string, status: string) => {
    setUpdatingId(obligationId);
    setError(null);
    try {
      await apiPatch<LegalObligation>(`/legal/obligations/${obligationId}/status`, token, { status });
      await loadWorkspace();
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Statusul nu a putut fi actualizat.");
    } finally {
      setUpdatingId(null);
    }
  };

  const markNotificationRead = async (notificationId: string) => {
    setReadingId(notificationId);
    setError(null);
    try {
      await apiPatch<Notification>(`/notifications/${notificationId}/read`, token, {});
      await loadWorkspace();
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
    try {
      await apiPost<LegalCase>("/legal/cases", token, {
        case_number: values.get("case_number"),
        court: values.get("court"),
        subject: values.get("subject"),
        filing_date: values.get("filing_date") || null,
      });
      form.reset();
      await loadWorkspace();
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
    try {
      await apiPost<LegalObligation>("/legal/obligations", token, {
        court_decision_id: values.get("court_decision_id"),
        obligation_type: values.get("obligation_type"),
        description: values.get("description"),
        due_date: values.get("due_date") || null,
      });
      form.reset();
      await loadWorkspace();
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
    const body = new FormData();
    body.set("entity_type", "LegalObligation");
    body.set("entity_id", obligationId);
    body.set("category", "SUPPORTING_DOCUMENT");
    body.set("file", file);
    try {
      await apiUpload("/documents", token, body);
      await loadWorkspace();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Documentul nu a putut fi încărcat.");
    } finally {
      setUploadingId(null);
    }
  };

  const createEnforcement = async (form: HTMLFormElement) => {
    const values = new FormData(form);
    setCreatingEnforcement(true);
    setError(null);
    try {
      await apiPost<EnforcementProceeding>("/legal/enforcements", token, {
        obligation_id: values.get("obligation_id"),
        file_number: values.get("file_number"),
        enforcement_officer: values.get("enforcement_officer") || null,
        start_date: values.get("start_date"),
      });
      form.reset();
      await loadWorkspace();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Procedura nu a putut fi creată.");
    } finally {
      setCreatingEnforcement(false);
    }
  };

  const createPenaltyRule = async (form: HTMLFormElement) => {
    const values = new FormData(form);
    setCreatingPenaltyRule(true);
    setError(null);
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
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Regula de penalizare nu a putut fi creată.");
    } finally {
      setCreatingPenaltyRule(false);
    }
  };

  const searchLegal = async () => {
    const query = searchQuery.trim();
    if (query.length < 2) {
      setError("Introdu cel puțin două caractere pentru căutare.");
      return;
    }
    setSearching(true);
    setError(null);
    try {
      const response = await apiGet<LegalSearchResponse>(`/search/legal?q=${encodeURIComponent(query)}`, token);
      setSearchResults(response.results);
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : "Căutarea nu a putut fi executată.");
    } finally {
      setSearching(false);
    }
  };

  const shownObligations = view === "obligations" ? data?.obligations ?? [] : (data?.obligations ?? []).slice(0, 5);

  return (
    <main className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/">GovControl</Link>
        <nav aria-label="Navigare principală">
          <Link className={view === "dashboard" ? "active" : ""} href="/legal">Panou GovLegal</Link>
          <Link className={view === "obligations" ? "active" : ""} href="/legal/obligations">Obligații</Link>
        </nav>
      </header>

      <section className="page-heading">
        <p className="eyebrow">GovLegal · mediu local</p>
        <h1>{view === "dashboard" ? "Control operațional" : "Obligații și termene"}</h1>
        <p>Dosare, obligații, executări și expuneri calculate din API-ul GovControl.</p>
      </section>

      <section className="connection-card" aria-label="Conectare API local">
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
            {loading ? "Se încarcă…" : "Actualizează"}
          </button>
        </div>
        <p>Tokenul este păstrat numai în localStorage-ul acestui browser local.</p>
      </section>

      {error ? <p className="notice error" role="alert">{error}</p> : null}

      <section className="search-card">
        <form onSubmit={(event) => { event.preventDefault(); void searchLegal(); }}>
          <label htmlFor="legal-search">Caută dosare sau obligații</label><div><input id="legal-search" onChange={(event) => setSearchQuery(event.target.value)} placeholder="Număr dosar sau text din obligație" value={searchQuery} /><button disabled={searching} type="submit">{searching ? "Caut…" : "Caută"}</button></div>
        </form>
        {searchResults.length ? <ul>{searchResults.map((item) => <li key={`${item.entity_type}-${item.id}`}><strong>{item.title}</strong><span>{item.entity_type} · {item.status}</span><p>{item.summary}</p></li>)}</ul> : null}
      </section>

      {data ? (
        <>
          <section className="metric-grid" aria-label="Indicatori obligații">
            <article><span>Obligații deschise</span><strong>{data.dashboard.open_obligations}</strong></article>
            <article className={data.dashboard.overdue_obligations ? "danger" : ""}><span>Depășite</span><strong>{data.dashboard.overdue_obligations}</strong></article>
            <article><span>Scadente în 7 zile</span><strong>{data.dashboard.due_within_seven_days}</strong></article>
            <article><span>Zile totale întârziere</span><strong>{data.dashboard.overdue_days_total}</strong></article>
          </section>

          <section className="content-grid">
            <article className="panel obligations-panel">
              <div className="panel-heading">
                <div><h2>{view === "obligations" ? "Toate obligațiile" : "Obligații prioritare"}</h2><p>{shownObligations.length} înregistrări</p></div>
                {view === "dashboard" ? <Link href="/legal/obligations">Vezi toate</Link> : null}
              </div>
              {shownObligations.length ? (
                <div className="table-wrap"><table><thead><tr><th>Obligație</th><th>Termen</th><th>Status</th><th>Document</th></tr></thead><tbody>
                  {shownObligations.map((item) => <tr key={item.id}><td><strong>{item.description}</strong><small>{item.obligation_type}</small></td><td className={isOverdue(item) ? "text-danger" : ""}>{formatDate(item.due_date)}</td><td><span className={`status status-${item.status.toLowerCase()}`}>{item.status}</span>{allowedStatuses[item.status].length ? <select aria-label={`Schimbă statusul obligației ${item.description}`} className="status-select" defaultValue="" disabled={updatingId === item.id} onChange={(event) => { if (event.target.value) void changeStatus(item.id, event.target.value); }}><option value="">Schimbă…</option>{allowedStatuses[item.status].map((status) => <option key={status} value={status}>{status}</option>)}</select> : null}</td><td><label className="upload-control">{uploadingId === item.id ? "Se încarcă…" : "Încarcă"}<input disabled={uploadingId === item.id} onChange={(event) => void uploadDocument(item.id, event.target.files?.[0])} type="file" /></label></td></tr>)}
                </tbody></table></div>
              ) : <p className="empty-state">Nu există încă obligații înregistrate pentru acest tenant.</p>}
            </article>

            {view === "dashboard" ? <aside className="side-column">
              <article className="panel"><h2>Dosare</h2><strong className="large-number">{data.cases.length}</strong><p>dosare accesibile în tenantul curent</p></article>
              <article className="panel"><h2>Executări</h2><strong className="large-number">{data.enforcements.length}</strong><p>proceduri active sau istorice</p></article>
              <article className="panel"><h2>Reguli de penalizare</h2><strong className="large-number">{data.penaltyRules.length}</strong><p>reguli disponibile pentru calculul expunerii</p></article>
              <article className="panel"><h2>Notificări</h2><strong className="large-number">{data.notifications.filter((item) => item.status === "UNREAD").length}</strong><p>alerte necitite privind termenele</p></article>
            </aside> : null}
          </section>

          {view === "dashboard" ? <section className="panel create-case-panel"><div className="panel-heading"><div><h2>Înregistrează dosar</h2><p>Dosarul devine imediat disponibil pentru hotărâri și obligații.</p></div></div>
            <form className="case-form" onSubmit={(event) => { event.preventDefault(); void createCase(event.currentTarget); }}>
              <label>Număr dosar<input name="case_number" required /></label>
              <label>Instanță<input name="court" required /></label>
              <label>Data înregistrării<input name="filing_date" type="date" /></label>
              <label className="wide">Obiect<textarea name="subject" required rows={2} /></label>
              <button disabled={creatingCase} type="submit">{creatingCase ? "Se creează…" : "Creează dosar"}</button>
            </form>
          </section> : null}

          {view === "dashboard" && data.cases.length ? <section className="panel create-case-panel"><div className="panel-heading"><div><h2>Înregistrează hotărâre</h2><p>Leagă hotărârea de un dosar din tenantul curent.</p></div></div>
            <form className="case-form" onSubmit={(event) => { event.preventDefault(); void createDecision(event.currentTarget); }}>
              <label>Dosar<select name="case_id" required><option value="">Alege dosarul…</option>{data.cases.map((item) => <option key={item.id} value={item.id}>{item.case_number} · {item.court}</option>)}</select></label>
              <label>Număr hotărâre<input name="decision_number" required /></label>
              <label>Data hotărârii<input name="decision_date" required type="date" /></label>
              <label>Tip hotărâre<input name="decision_type" placeholder="Sentință" required /></label>
              <label>Data rămânerii definitive<input name="final_date" type="date" /></label>
              <label className="wide">Rezumat<textarea name="summary" rows={2} /></label>
              <button disabled={creatingDecision} type="submit">{creatingDecision ? "Se creează…" : "Creează hotărâre"}</button>
            </form>
          </section> : null}

          {view === "obligations" && data.decisions.length ? <section className="panel create-case-panel"><div className="panel-heading"><div><h2>Adaugă obligație</h2><p>Termenul va fi urmărit automat în dashboard și notificări.</p></div></div>
            <form className="case-form" onSubmit={(event) => { event.preventDefault(); void createObligation(event.currentTarget); }}>
              <label>Hotărâre<select name="court_decision_id" required><option value="">Alege hotărârea…</option>{data.decisions.map((item) => <option key={item.id} value={item.id}>{item.decision_number} · {item.decision_type}</option>)}</select></label>
              <label>Tip obligație<select defaultValue="DO" name="obligation_type"><option value="DO">Executare</option><option value="PAY">Plată</option><option value="REFRAIN">Abținere</option><option value="RESOLVE_REQUEST">Soluționare cerere</option><option value="ISSUE_DOCUMENT">Emiterea documentului</option><option value="OTHER">Alt tip</option></select></label>
              <label>Termen<input name="due_date" type="date" /></label>
              <label className="wide">Descriere<textarea name="description" required rows={2} /></label>
              <button disabled={creatingObligation} type="submit">{creatingObligation ? "Se creează…" : "Creează obligație"}</button>
            </form>
          </section> : null}

          {view === "obligations" && data.obligations.length ? <section className="panel create-case-panel"><div className="panel-heading"><div><h2>Deschide executare</h2><p>Înregistrează procedura aferentă unei obligații existente.</p></div></div>
            <form className="case-form" onSubmit={(event) => { event.preventDefault(); void createEnforcement(event.currentTarget); }}>
              <label>Obligație<select name="obligation_id" required><option value="">Alege obligația…</option>{data.obligations.map((item) => <option key={item.id} value={item.id}>{item.description.slice(0, 70)}</option>)}</select></label>
              <label>Număr dosar executare<input name="file_number" required /></label>
              <label>Data deschiderii<input name="start_date" required type="date" /></label>
              <label>Executor / responsabil<input name="enforcement_officer" /></label>
              <button disabled={creatingEnforcement} type="submit">{creatingEnforcement ? "Se creează…" : "Deschide executare"}</button>
            </form>
          </section> : null}

          {view === "obligations" && data.obligations.length ? <section className="panel create-case-panel"><div className="panel-heading"><div><h2>Regulă de penalizare</h2><p>Expunerea se calculează derivat, fără a persista o sumă agregată.</p></div></div>
            <form className="case-form" onSubmit={(event) => { event.preventDefault(); void createPenaltyRule(event.currentTarget); }}>
              <label>Obligație<select name="obligation_id" required><option value="">Alege obligația…</option>{data.obligations.map((item) => <option key={item.id} value={item.id}>{item.description.slice(0, 70)}</option>)}</select></label>
              <label>Metodă<select defaultValue="DAILY_AMOUNT" name="calculation_type"><option value="DAILY_AMOUNT">Sumă pe zi</option><option value="PERCENTAGE_OF_BASE">Procent din bază / zi</option></select></label>
              <label>Data început<input name="start_date" required type="date" /></label>
              <label>Sumă zilnică<input min="0" name="daily_amount" step="0.01" type="number" /></label>
              <label>Procent zilnic<input min="0" name="percentage" step="0.0001" type="number" /></label>
              <label>Valoare bază<input min="0" name="base_value" step="0.01" type="number" /></label>
              <label>Data sfârșit<input name="end_date" type="date" /></label>
              <button disabled={creatingPenaltyRule} type="submit">{creatingPenaltyRule ? "Se creează…" : "Creează regulă"}</button>
            </form>
          </section> : null}

          {view === "dashboard" ? <section className="panel audit-panel"><div className="panel-heading"><div><h2>Activitate recentă</h2><p>Jurnalul de audit al tenantului</p></div></div>
            {data.auditEvents.length ? <ul className="audit-list">{data.auditEvents.slice(0, 6).map((event) => <li key={event.id}><strong>{event.action}</strong><span>{event.entity_type}</span><time>{new Intl.DateTimeFormat("ro-RO", { dateStyle: "medium", timeStyle: "short" }).format(new Date(event.created_at))}</time></li>)}</ul> : <p className="empty-state">Nu există evenimente de audit încă.</p>}
          </section> : null}
          {view === "dashboard" ? <section className="panel notifications-panel"><div className="panel-heading"><div><h2>Notificări</h2><p>Alerte de termen pentru utilizatorul curent</p></div></div>
            {data.notifications.length ? <ul className="notification-list">{data.notifications.slice(0, 6).map((item) => <li className={item.status === "UNREAD" ? "unread" : ""} key={item.id}><div><strong>{item.title}</strong><p>{item.body}</p></div>{item.status === "UNREAD" ? <button disabled={readingId === item.id} onClick={() => void markNotificationRead(item.id)} type="button">{readingId === item.id ? "Se salvează…" : "Marchează citită"}</button> : <span>Citită</span>}</li>)}</ul> : <p className="empty-state">Nu există notificări pentru utilizatorul curent.</p>}
          </section> : null}
        </>
      ) : !error && !loading ? <p className="notice">Introdu tokenul local pentru a vedea datele operaționale.</p> : null}
    </main>
  );
}
