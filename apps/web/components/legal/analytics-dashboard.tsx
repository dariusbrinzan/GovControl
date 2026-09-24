"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { apiGet, buildQuery, type AnalyticsFilterOptions, type LegalAnalytics } from "../../lib/api";
import { downloadCsv, formatCurrency } from "../../lib/legal";
import { CalendarClock, CircleDollarSign, FileCheck2, Gavel } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { useSession } from "./session-provider";

const chartColors = ["#2563eb", "#dc2626", "#d97706", "#0f766e", "#7c3aed", "#64748b"];
function monthLabel(value: string): string {
  return new Intl.DateTimeFormat("ro-RO", { month: "short", year: "2-digit" }).format(new Date(`${value}T00:00:00`));
}

function ChartPanel({ title, description, children, table, empty = false }: {
  title: string; description: string; children: React.ReactNode; table: React.ReactNode; empty?: boolean;
}) {
  return <article className="chart-panel"><header><div><h2>{title}</h2><p>{description}</p></div></header><div className="chart-canvas">{empty ? <div className="chart-empty"><FileCheck2 size={24} /><strong>Nu există date în perioada selectată</strong><span>Modifică filtrele sau adaugă înregistrări operaționale.</span></div> : children}</div><details className="chart-data"><summary>Vezi datele din grafic</summary>{table}</details></article>;
}

export default function AnalyticsDashboard() {
  const { token, user, ready } = useSession();
  const [analytics, setAnalytics] = useState<LegalAnalytics | null>(null);
  const [options, setOptions] = useState<AnalyticsFilterOptions | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({ date_from: "", date_to: "", department_id: "", responsible_user_id: "", court: "", obligation_status: "" });

  const load = useCallback(async () => {
    if (!token || !user?.permissions.includes("legal.report")) return;
    setLoading(true); setError(null);
    try {
      setAnalytics(await apiGet<LegalAnalytics>(`/legal/analytics/dashboard${buildQuery(filters)}`, token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Raportul nu a putut fi încărcat.");
    } finally { setLoading(false); }
  }, [filters, token, user]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (token && user?.permissions.includes("legal.report")) {
      void apiGet<AnalyticsFilterOptions>("/legal/analytics/filters", token).then(setOptions).catch(() => setOptions(null));
    }
  }, [token, user]);

  const monthlyData = useMemo(() => analytics?.monthly_activity.map((item) => ({ ...item, label: monthLabel(item.month) })) ?? [], [analytics]);
  const exportReport = () => {
    if (!analytics) return;
    downloadCsv(`govlegal-raport-${analytics.generated_on}.csv`, [
      ["Indicator", "Valoare"],
      ["Obligații active", analytics.kpis.active_obligations],
      ["Obligații depășite", analytics.kpis.overdue_obligations],
      ["Scadente în 7 zile", analytics.kpis.due_within_seven_days],
      ["Executări active", analytics.kpis.active_enforcements],
      ["Expunere financiară (RON)", analytics.kpis.financial_exposure],
      ["Rată de finalizare (%)", analytics.kpis.completion_rate],
    ]);
  };

  return <>
    <PageHeader eyebrow="GovLegal · monitorizare instituțională" title="Panou de control juridic" description="O imagine operațională asupra termenelor, riscului și volumului de lucru al instituției." actions={<><button className="button secondary" disabled={!analytics} onClick={exportReport}>Exportă CSV</button><Link className="button primary" href="/legal/obligations">Vezi obligațiile</Link></>} />
    <form className="analytics-filters" onSubmit={(event) => { event.preventDefault(); void load(); }}>
      <label>De la<input type="date" value={filters.date_from} onChange={(event) => setFilters((current) => ({ ...current, date_from: event.target.value }))} /></label>
      <label>Până la<input type="date" value={filters.date_to} onChange={(event) => setFilters((current) => ({ ...current, date_to: event.target.value }))} /></label>
      <label>Departament<select value={filters.department_id} onChange={(event) => setFilters((current) => ({ ...current, department_id: event.target.value, responsible_user_id: "" }))}><option value="">Toate departamentele</option>{options?.departments.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label>Responsabil<select value={filters.responsible_user_id} onChange={(event) => setFilters((current) => ({ ...current, responsible_user_id: event.target.value }))}><option value="">Toți responsabilii</option>{options?.users.filter((item) => !filters.department_id || item.department_id === filters.department_id).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label>Instanță<select value={filters.court} onChange={(event) => setFilters((current) => ({ ...current, court: event.target.value }))}><option value="">Toate instanțele</option>{options?.courts.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label>Status<select value={filters.obligation_status} onChange={(event) => setFilters((current) => ({ ...current, obligation_status: event.target.value }))}><option value="">Toate statusurile</option>{options?.statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <button className="button secondary" type="submit">Aplică filtrele</button>
    </form>

    {!ready || loading ? <LoadingState label="Calculăm indicatorii instituției…" /> : null}
    {ready && !user ? <EmptyState title="Conectează aplicația" description="Introdu tokenul local din fereastra de conectare pentru a vedea indicatorii reali." icon={<Gavel size={25} />} /> : null}
    {user && !user.permissions.includes("legal.report") ? <ErrorState message="Rolul curent nu are permisiunea legal.report." /> : null}
    {error ? <ErrorState message={error} retry={() => void load()} /> : null}
    {analytics && !loading ? <>
      <section className="kpi-grid" aria-label="Indicatori principali">
        <Link href="/legal/obligations?scope=active"><article className="kpi-card"><span className="kpi-icon blue"><FileCheck2 size={20} /></span><div><small>Obligații active</small><strong>{analytics.kpis.active_obligations}</strong><p>în perioada selectată</p></div></article></Link>
        <Link href="/legal/deadlines?scope=overdue"><article className="kpi-card danger"><span className="kpi-icon red"><CalendarClock size={20} /></span><div><small>Termene depășite</small><strong>{analytics.kpis.overdue_obligations}</strong><p>necesită intervenție</p></div></article></Link>
        <Link href="/legal/deadlines?scope=upcoming"><article className="kpi-card"><span className="kpi-icon amber"><CalendarClock size={20} /></span><div><small>Scadente în 7 zile</small><strong>{analytics.kpis.due_within_seven_days}</strong><p>priorități apropiate</p></div></article></Link>
        <Link href="/legal/enforcements"><article className="kpi-card"><span className="kpi-icon violet"><Gavel size={20} /></span><div><small>Executări active</small><strong>{analytics.kpis.active_enforcements}</strong><p>proceduri în desfășurare</p></div></article></Link>
        <Link href="/legal/penalties"><article className="kpi-card wide"><span className="kpi-icon teal"><CircleDollarSign size={20} /></span><div><small>Expunere financiară estimată</small><strong>{formatCurrency(analytics.kpis.financial_exposure)}</strong><p>calculată la {analytics.generated_on}</p></div></article></Link>
        <article className="kpi-card"><span className="completion-ring" style={{ "--progress": `${analytics.kpis.completion_rate * 3.6}deg` } as React.CSSProperties}>{analytics.kpis.completion_rate}%</span><div><small>Rată de finalizare</small><p>obligații închise în perioadă</p></div></article>
      </section>

      <section className="charts-grid">
        <ChartPanel empty={!monthlyData.some((item) => item.created || item.completed || item.active_at_end)} title="Evoluția obligațiilor" description="Obligații create, finalizate și active la sfârșitul lunii." table={<SimpleTable headers={["Lună", "Create", "Finalizate", "Active"]} rows={monthlyData.map((row) => [row.label, row.created, row.completed, row.active_at_end])} />}>
          <ResponsiveContainer width="100%" height="100%"><AreaChart data={monthlyData} accessibilityLayer><defs><linearGradient id="activeFill" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#2563eb" stopOpacity={0.3}/><stop offset="95%" stopColor="#2563eb" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tickLine={false} axisLine={false} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} /><Tooltip /><Legend /><Area isAnimationActive={false} name="Active" type="monotone" dataKey="active_at_end" stroke="#2563eb" fill="url(#activeFill)" strokeWidth={2} /><Area isAnimationActive={false} name="Finalizate" type="monotone" dataKey="completed" stroke="#0f766e" fill="transparent" strokeWidth={2} /></AreaChart></ResponsiveContainer>
        </ChartPanel>
        <ChartPanel empty={!analytics.deadline_distribution.some((item) => item.value)} title="Distribuția termenelor" description="Poziționarea obligațiilor active față de scadență." table={<SimpleTable headers={["Interval", "Obligații"]} rows={analytics.deadline_distribution.map((row) => [row.label, row.value])} />}>
          <ResponsiveContainer width="100%" height="100%"><PieChart accessibilityLayer><Pie isAnimationActive={false} data={analytics.deadline_distribution} dataKey="value" nameKey="label" innerRadius={58} outerRadius={88} paddingAngle={2}>{analytics.deadline_distribution.map((entry, index) => <Cell key={entry.key} fill={chartColors[index % chartColors.length]} />)}</Pie><Tooltip /><Legend verticalAlign="bottom" height={44} /></PieChart></ResponsiveContainer>
        </ChartPanel>
        <ChartPanel empty={!analytics.workload_by_department.length} title="Volum pe departamente" description="Obligații active și depășite, comparate pe structuri." table={<SimpleTable headers={["Departament", "Active", "Depășite", "Finalizate"]} rows={analytics.workload_by_department.map((row) => [row.label, row.active, row.overdue, row.completed])} />}>
          <ResponsiveContainer width="100%" height="100%"><BarChart data={analytics.workload_by_department} layout="vertical" accessibilityLayer><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" allowDecimals={false} /><YAxis type="category" dataKey="label" width={110} tickLine={false} /><Tooltip /><Legend /><Bar isAnimationActive={false} name="Active" dataKey="active" fill="#2563eb" radius={[0, 4, 4, 0]} /><Bar isAnimationActive={false} name="Depășite" dataKey="overdue" fill="#dc2626" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer>
        </ChartPanel>
        <ChartPanel empty={!analytics.overdue_ageing.some((item) => item.value)} title="Vechimea restanțelor" description="De cât timp sunt depășite obligațiile încă active." table={<SimpleTable headers={["Vechime", "Obligații"]} rows={analytics.overdue_ageing.map((row) => [row.label, row.value])} />}>
          <ResponsiveContainer width="100%" height="100%"><BarChart data={analytics.overdue_ageing} accessibilityLayer><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tickLine={false} /><YAxis allowDecimals={false} /><Tooltip /><Bar isAnimationActive={false} dataKey="value" name="Obligații" fill="#d97706" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer>
        </ChartPanel>
      </section>
      <p className="report-footnote">Raport generat la {analytics.generated_on}. Selectează un indicator pentru drill-down în lista operațională.</p>
    </> : null}
  </>;
}

function SimpleTable({ headers, rows }: { headers: string[]; rows: Array<Array<string | number>> }) {
  return <div className="table-wrap compact"><table><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div>;
}
