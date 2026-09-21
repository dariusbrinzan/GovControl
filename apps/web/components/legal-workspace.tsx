"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  apiGet,
  apiPatch,
  type AuditEvent,
  type AuditEventPage,
  type EnforcementProceeding,
  type LegalCase,
  type LegalDashboard,
  type LegalObligation,
  type Notification,
  type PenaltyRule,
} from "../lib/api";

type WorkspaceData = {
  dashboard: LegalDashboard;
  obligations: LegalObligation[];
  cases: LegalCase[];
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

  useEffect(() => setToken(window.localStorage.getItem(tokenStorageKey) ?? ""), []);

  const loadWorkspace = useCallback(async () => {
    if (!token.trim()) {
      setError("Introdu tokenul DEV_AUTH_TOKEN din fișierul .env pentru a încărca datele.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [dashboard, obligations, cases, enforcements, penaltyRules, auditEvents, notifications] = await Promise.all([
        apiGet<LegalDashboard>("/legal/dashboard", token),
        apiGet<LegalObligation[]>("/legal/obligations", token),
        apiGet<LegalCase[]>("/legal/cases", token),
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
                <div className="table-wrap"><table><thead><tr><th>Obligație</th><th>Termen</th><th>Status</th></tr></thead><tbody>
                  {shownObligations.map((item) => <tr key={item.id}><td><strong>{item.description}</strong><small>{item.obligation_type}</small></td><td className={isOverdue(item) ? "text-danger" : ""}>{formatDate(item.due_date)}</td><td><span className={`status status-${item.status.toLowerCase()}`}>{item.status}</span>{allowedStatuses[item.status].length ? <select aria-label={`Schimbă statusul obligației ${item.description}`} className="status-select" defaultValue="" disabled={updatingId === item.id} onChange={(event) => { if (event.target.value) void changeStatus(item.id, event.target.value); }}><option value="">Schimbă…</option>{allowedStatuses[item.status].map((status) => <option key={status} value={status}>{status}</option>)}</select> : null}</td></tr>)}
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
