"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  notificationsGet, notificationsPatch, notificationsPost, notificationsPut,
  type NotificationItem, type NotificationPage, type NotificationPreference,
  type NotificationSeverity, type NotificationStatus,
} from "../../lib/notifications";
import { useSession } from "../legal/session-provider";
import { ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { StatusBadge } from "../ui/status-badge";

const PAGE_SIZE = 20;
const categories = ["", "LEGAL", "CONTRACTS", "DOCUMENTS", "ADMINISTRATIVE", "SECURITY"];
const severities: Array<"" | NotificationSeverity> = ["", "INFO", "SUCCESS", "WARNING", "CRITICAL"];
const statuses: Array<"" | NotificationStatus> = ["", "UNREAD", "READ", "ARCHIVED"];

function formatDate(value: string | null): string {
  return value
    ? new Intl.DateTimeFormat("ro-RO", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
    : "—";
}

export function NotificationCenter({ module }: { module: "legal" | "contracts" }) {
  const { token, user, ready } = useSession();
  const [page, setPage] = useState<NotificationPage | null>(null);
  const [preferences, setPreferences] = useState<NotificationPreference[]>([]);
  const [status, setStatus] = useState<"" | NotificationStatus>("");
  const [category, setCategory] = useState(module === "contracts" ? "CONTRACTS" : "");
  const [severity, setSeverity] = useState<"" | NotificationSeverity>("");
  const [dateFrom, setDateFrom] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const canRead = user?.permissions.includes("notifications.read") ?? false;
  const canManage = user?.permissions.includes("notifications.manage") ?? false;
  const canPreferences = user?.permissions.includes("notifications.preferences") ?? false;

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (status) params.set("status", status);
    if (category) params.set("category", category);
    if (severity) params.set("severity", severity);
    if (dateFrom) params.set("created_from", new Date(`${dateFrom}T00:00:00`).toISOString());
    return `?${params.toString()}`;
  }, [category, dateFrom, offset, severity, status]);

  const load = useCallback(async (quiet = false) => {
    if (!user || !canRead) { setLoading(false); return; }
    if (!quiet) setLoading(true);
    try {
      const [result, preferenceResult] = await Promise.all([
        notificationsGet<NotificationPage>(query),
        canPreferences ? notificationsGet<NotificationPreference[]>("/preferences") : Promise.resolve([]),
      ]);
      setPage(result); setPreferences(preferenceResult); setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Notificările nu pot fi încărcate.");
    } finally { if (!quiet) setLoading(false); }
  }, [canPreferences, canRead, query, user]);

  useEffect(() => { if (ready) void load(); }, [load, ready]);
  useEffect(() => {
    if (!canRead) return;
    const refresh = () => { if (document.visibilityState === "visible") void load(true); };
    const interval = window.setInterval(refresh, 60_000);
    document.addEventListener("visibilitychange", refresh);
    return () => { window.clearInterval(interval); document.removeEventListener("visibilitychange", refresh); };
  }, [canRead, load]);

  const mutate = async (item: NotificationItem, action: string) => {
    setBusy(item.id); setSuccess(null);
    try {
      await notificationsPatch(`/${item.id}/${action}`, token);
      setSuccess("Starea notificării a fost actualizată."); await load(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Actualizarea nu a reușit."); }
    finally { setBusy(null); }
  };
  const markAll = async () => {
    setBusy("all");
    try {
      const result = await notificationsPost<{ updated: number }>("/mark-all-read", token);
      setSuccess(`${result.updated} notificări au fost marcate ca citite.`); await load(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Actualizarea în masă nu a reușit."); }
    finally { setBusy(null); }
  };
  const togglePreference = async (name: string, enabled: boolean) => {
    setBusy(`preference:${name}`);
    try {
      await notificationsPut("/preferences", token, {
        category: name, channel: "IN_APP", enabled,
        quiet_hours_start: null, quiet_hours_end: null,
      });
      setSuccess("Preferința a fost salvată."); await load(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Preferința nu a putut fi salvată."); }
    finally { setBusy(null); }
  };
  const filter = (change: () => void) => { change(); setOffset(0); };

  if (!ready || loading) return <LoadingState />;
  if (user && !canRead) return <ErrorState message="Rolul curent nu are permisiunea notifications.read." />;

  return <>
    <PageHeader eyebrow="GovNotifications" title={module === "contracts" ? "Notificări contractuale" : "Centrul de notificări"} description="Inbox instituțional unificat, filtrat după tenant și destinatar." />
    {error ? <ErrorState message={error} retry={() => void load()} /> : null}
    {success ? <div className="notice success" role="status">{success}</div> : null}
    <section className="notification-toolbar" aria-label="Filtre notificări">
      <label>Stare<select value={status} onChange={(event) => filter(() => setStatus(event.target.value as "" | NotificationStatus))}>{statuses.map((value) => <option key={value || "all"} value={value}>{value || "Toate"}</option>)}</select></label>
      <label>Categorie<select value={category} onChange={(event) => filter(() => setCategory(event.target.value))}>{categories.map((value) => <option key={value || "all"} value={value}>{value || "Toate"}</option>)}</select></label>
      <label>Severitate<select value={severity} onChange={(event) => filter(() => setSeverity(event.target.value as "" | NotificationSeverity))}>{severities.map((value) => <option key={value || "all"} value={value}>{value || "Toate"}</option>)}</select></label>
      <label>Începând cu<input type="date" value={dateFrom} onChange={(event) => filter(() => setDateFrom(event.target.value))} /></label>
      {canManage ? <button className="button secondary" disabled={busy === "all"} onClick={() => void markAll()}>Marchează toate citite</button> : null}
    </section>
    {!page?.items.length && !error ? <section className="empty-state-card"><strong>Nu există notificări pentru filtrele curente.</strong><p>Notificările noi vor apărea automat, fără polling agresiv.</p></section> : null}
    {page?.items.length ? <section className="notification-layout"><div className="notification-feed">
      {page.items.map((item) => <article className={`notification-card severity-${item.severity.toLowerCase()} ${item.status === "UNREAD" ? "unread" : ""}`} key={item.id}>
        <div className="notification-card-head"><div><span>{item.category}</span><time>{formatDate(item.created_at)}</time></div><StatusBadge status={item.status} /></div>
        <h2>{item.title}</h2><p>{item.body}</p><div className="notification-actions">
          {item.resource_url ? <Link href={item.resource_url}>Deschide resursa</Link> : <span>Resursa poate fi indisponibilă temporar.</span>}
          {canManage && item.status === "UNREAD" ? <button disabled={busy === item.id} onClick={() => void mutate(item, "read")}>Marchează citită</button> : null}
          {canManage && item.status === "READ" ? <button disabled={busy === item.id} onClick={() => void mutate(item, "unread")}>Marchează necitită</button> : null}
          {canManage && item.status !== "ARCHIVED" ? <button disabled={busy === item.id} onClick={() => void mutate(item, "archive")}>Arhivează</button> : null}
          {canManage && item.status === "ARCHIVED" ? <button disabled={busy === item.id} onClick={() => void mutate(item, "restore")}>Restaurează</button> : null}
        </div>
      </article>)}
      <div className="pagination"><button className="button secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Anterior</button><span>{offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} din {page.total}</span><button className="button secondary" disabled={offset + PAGE_SIZE >= page.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Următor</button></div>
    </div>{canPreferences ? <aside className="notification-preferences"><h2>Preferințe IN_APP</h2><p>Alege categoriile afișate în inbox.</p>{categories.filter(Boolean).map((name) => { const preference = preferences.find((item) => item.category === name && item.channel === "IN_APP"); const enabled = preference?.enabled ?? true; return <label key={name}><span>{name}</span><input checked={enabled} disabled={busy === `preference:${name}`} onChange={(event) => void togglePreference(name, event.target.checked)} type="checkbox" /></label>; })}</aside> : null}</section> : null}
  </>;
}
