"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { insightsGet, type InsightsDashboard } from "../../lib/insights";
import {
  CalendarClock,
  CircleDollarSign,
  Database,
  LayoutDashboard,
} from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { useSession } from "../legal/session-provider";

const colors = [
  "#2563eb",
  "#0f766e",
  "#d97706",
  "#7c3aed",
  "#dc2626",
  "#64748b",
];
const modules = ["legal", "contracts", "documents", "notifications"] as const;
const moduleLabels: Record<string, string> = {
  legal: "GovLegal",
  contracts: "GovContracts",
  documents: "GovDocuments",
  notifications: "GovNotifications",
};
const metricLabels: Record<string, string> = {
  active_obligations: "Obligații active",
  active_enforcements: "Executări active",
  overdue_milestones: "Jaloane restante",
  overdue_contract_obligations: "Obligații contractuale restante",
  overdue_payments: "Plăți restante",
  documents_available: "Documente disponibile",
  documents_processing: "Documente în procesare",
  documents_rejected: "Documente respinse",
  documents_archived: "Documente arhivate",
  notifications_unread: "Notificări necitite",
  deliveries_succeeded: "Livrări reușite",
  deliveries_failed: "Livrări eșuate",
  dead_letter_events: "Evenimente în DLQ",
};

function DataTable({
  headers,
  rows,
  linkForRow,
}: {
  headers: string[];
  rows: Array<Array<string | number>>;
  linkForRow?: (row: Array<string | number>) => string;
}) {
  return (
    <div className="table-wrap compact">
      <table>
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row[0]}-${index}`}>
              {row.map((cell, cellIndex) => {
                const content =
                  cellIndex === 0 && linkForRow ? (
                    <Link href={linkForRow(row)}>{cell}</Link>
                  ) : (
                    cell
                  );
                return <td key={`${cell}-${cellIndex}`}>{content}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChartPanel({
  title,
  description,
  children,
  table,
  empty,
}: {
  title: string;
  description: string;
  children: ReactNode;
  table: ReactNode;
  empty: boolean;
}) {
  return (
    <article className="chart-panel">
      <header>
        <h2>{title}</h2>
        <p>{description}</p>
      </header>
      <div className="chart-canvas">
        {empty ? (
          <div className="chart-empty">
            <Database size={24} />
            <strong>Nu există date pentru selecția curentă</strong>
            <span>Modifică perioada sau filtrele aplicate.</span>
          </div>
        ) : (
          children
        )}
      </div>
      <details className="chart-data">
        <summary>Vezi datele din grafic</summary>
        {table}
      </details>
    </article>
  );
}

export function InsightsDashboardView({ module }: { module?: string }) {
  const { user, ready } = useSession();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [data, setData] = useState<InsightsDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState(searchParams.get("date_from") ?? "");
  const [dateTo, setDateTo] = useState(searchParams.get("date_to") ?? "");

  const query = useMemo(() => {
    const value = new URLSearchParams();
    if (searchParams.get("date_from"))
      value.set("date_from", searchParams.get("date_from")!);
    if (searchParams.get("date_to"))
      value.set("date_to", searchParams.get("date_to")!);
    const encoded = value.toString();
    return encoded ? `?${encoded}` : "";
  }, [searchParams]);

  const load = useCallback(async () => {
    if (!user?.permissions.includes("insights.read")) return;
    setLoading(true);
    setError(null);
    try {
      setData(
        await insightsGet<InsightsDashboard>(
          `/dashboards/${module ?? "executive"}${query}`,
        ),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Dashboardul nu este disponibil.",
      );
    } finally {
      setLoading(false);
    }
  }, [module, query, user]);

  useEffect(() => {
    void load();
  }, [load]);

  const applyFilters = () => {
    const value = new URLSearchParams();
    if (dateFrom) value.set("date_from", dateFrom);
    if (dateTo) value.set("date_to", dateTo);
    router.replace(`${pathname}${value.size ? `?${value}` : ""}`);
  };
  const singleExposure =
    data?.financial_exposure.length === 1 ? data.financial_exposure[0] : null;
  const financialSeries =
    data?.financial_exposure.map((item) => ({
      ...item,
      key: `${item.category} · ${item.currency}`,
    })) ?? [];
  const metrics = data?.operational_metrics ?? {};
  const contractExpiry = [7, 30, 60, 90].map((days) =>
    Number(metrics[`expiring_contracts_${days}`] ?? 0),
  );
  const dueCumulative = data
    ? [data.due_soon_7, data.due_soon_30, data.due_soon_60, data.due_soon_90]
    : [0, 0, 0, 0];
  const cumulative = module === "contracts" ? contractExpiry : dueCumulative;
  const deadlineSeries = [
    { key: "0–7 zile", count: cumulative[0] },
    { key: "8–30 zile", count: Math.max(0, cumulative[1] - cumulative[0]) },
    { key: "31–60 zile", count: Math.max(0, cumulative[2] - cumulative[1]) },
    { key: "61–90 zile", count: Math.max(0, cumulative[3] - cumulative[2]) },
  ];
  const metricKeys =
    module === "legal"
      ? ["active_obligations", "active_enforcements"]
      : module === "contracts"
        ? ["overdue_milestones", "overdue_contract_obligations", "overdue_payments"]
        : module === "documents"
          ? [
              "documents_available",
              "documents_processing",
              "documents_rejected",
              "documents_archived",
            ]
          : module === "notifications"
            ? [
                "notifications_unread",
                "deliveries_succeeded",
                "deliveries_failed",
                "dead_letter_events",
              ]
            : [
                "active_obligations",
                "overdue_payments",
                "documents_rejected",
                "deliveries_failed",
              ];
  const operationalSeries = metricKeys.map((key) => ({
    key: metricLabels[key],
    count: Number(metrics[key] ?? 0),
  }));
  const title = module
    ? `Dashboard ${moduleLabels[module] ?? module}`
    : "Dashboard executiv instituțional";
  const drillDown = (filter: "status" | "resource_type", value: string | number) => {
    const next = new URLSearchParams({ [filter]: String(value), limit: "25" });
    if (module) next.set("module", module);
    if (dateFrom) next.set("date_from", dateFrom);
    if (dateTo) next.set("date_to", dateTo);
    return `/insights/search?${next}`;
  };

  return (
    <>
      <PageHeader
        eyebrow="GovInsights · intelligence operațional"
        title={title}
        description="Indicatori consolidați din proiecții tenant-scoped, fără interogări directe în bazele modulelor sursă."
        actions={
          <Link className="button primary" href="/insights/reports">
            Construiește raport
          </Link>
        }
      />
      <nav className="insights-tabs" aria-label="Dashboarduri GovInsights">
        <Link className={!module ? "active" : ""} href="/insights">
          Executiv
        </Link>
        {modules.map((key) => (
          <Link
            className={module === key ? "active" : ""}
            href={`/insights/${key}`}
            key={key}
          >
            {moduleLabels[key]}
          </Link>
        ))}
      </nav>
      <form
        className="analytics-filters"
        onSubmit={(event) => {
          event.preventDefault();
          applyFilters();
        }}
      >
        <label>
          De la
          <input
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
          />
        </label>
        <label>
          Până la
          <input
            type="date"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
          />
        </label>
        <button className="button secondary" type="submit">
          Aplică perioada
        </button>
        <button
          className="button ghost"
          type="button"
          onClick={() => {
            setDateFrom("");
            setDateTo("");
            router.replace(pathname);
          }}
        >
          Resetează
        </button>
      </form>
      {!ready || loading ? (
        <LoadingState label="Actualizăm indicatorii GovInsights…" />
      ) : null}
      {ready && user && !user.permissions.includes("insights.read") ? (
        <ErrorState message="Rolul curent nu are permisiunea insights.read." />
      ) : null}
      {error ? <ErrorState message={error} retry={() => void load()} /> : null}
      {data && !loading ? (
        <>
          <div
            className={`projection-banner ${data.stale ? "stale" : "fresh"}`}
            role="status"
          >
            <Database size={16} />
            <span>
              {data.stale
                ? "Datele pot fi neactualizate"
                : "Proiecții sincronizate"}
            </span>
            <small>
              Ultima actualizare:{" "}
              {data.last_updated_at
                ? new Date(data.last_updated_at).toLocaleString("ro-RO")
                : "în așteptare"}{" "}
              · versiunea {data.projection_version}
            </small>
          </div>
          <section className="kpi-grid" aria-label="Indicatori GovInsights">
            <article className="kpi-card">
              <span className="kpi-icon blue">
                <LayoutDashboard size={20} />
              </span>
              <div>
                <small>Resurse monitorizate</small>
                <strong>{data.total.toLocaleString("ro-RO")}</strong>
                <p>
                  {data.period_total} în perioada curentă ·{" "}
                  {data.period_change_percent === null
                    ? "fără bază de comparație"
                    : `${data.period_change_percent > 0 ? "+" : ""}${data.period_change_percent}% față de perioada anterioară`}
                </p>
              </div>
            </article>
            <article className="kpi-card danger">
              <span className="kpi-icon red">
                <CalendarClock size={20} />
              </span>
              <div>
                <small>Termene depășite</small>
                <strong>{data.overdue}</strong>
                <p>necesită analiză operațională</p>
              </div>
            </article>
            <article className="kpi-card">
              <span className="kpi-icon amber">
                <CalendarClock size={20} />
              </span>
              <div>
                <small>Scadente în 30 zile</small>
                <strong>{data.due_soon_30}</strong>
                <p>{data.due_soon_7} în următoarele 7 zile</p>
              </div>
            </article>
            <article className="kpi-card wide">
              <span className="kpi-icon teal">
                <CircleDollarSign size={20} />
              </span>
              <div>
                <small>Valori financiare</small>
                <strong>
                  {singleExposure
                    ? `${Number(singleExposure.amount).toLocaleString("ro-RO")} ${singleExposure.currency}`
                    : `${data.financial_exposure.length} serii separate`}
                </strong>
                <p>monedele și categoriile nu sunt combinate</p>
              </div>
            </article>
          </section>
          {data.total === 0 ? (
            <EmptyState
              title="Proiecția este goală"
              description="Rulează backfill-ul sau creează înregistrări în modulele operaționale."
              icon={<Database size={25} />}
            />
          ) : (
            <section className="charts-grid">
              <ChartPanel
                title="Distribuție pe status"
                description="Starea curentă a resurselor proiectate."
                empty={!data.by_status.length}
                table={
                  <DataTable
                    headers={["Status", "Total"]}
                    rows={data.by_status.map((row) => [row.key, row.count])}
                    linkForRow={(row) => drillDown("status", row[0])}
                  />
                }
              >
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart accessibilityLayer>
                    <Pie
                      data={data.by_status}
                      dataKey="count"
                      nameKey="key"
                      innerRadius={58}
                      outerRadius={88}
                    >
                      {data.by_status.map((entry, index) => (
                        <Cell
                          key={entry.key}
                          fill={colors[index % colors.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </ChartPanel>
              <ChartPanel
                title="Portofoliu pe tipuri"
                description="Volumul resurselor pe categorii operaționale."
                empty={!data.by_type.length}
                table={
                  <DataTable
                    headers={["Tip", "Total"]}
                    rows={data.by_type.map((row) => [row.key, row.count])}
                    linkForRow={(row) => drillDown("resource_type", row[0])}
                  />
                }
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.by_type} accessibilityLayer>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="key" tickLine={false} />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar
                      dataKey="count"
                      name="Resurse"
                      fill="#2563eb"
                      radius={[5, 5, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </ChartPanel>
              <ChartPanel
                title="Evoluție lunară"
                description="Volumul resurselor înregistrate în fiecare lună."
                empty={!data.monthly_trend.length}
                table={
                  <DataTable
                    headers={["Lună", "Total"]}
                    rows={data.monthly_trend.map((row) => [
                      row.month,
                      row.count,
                    ])}
                  />
                }
              >
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.monthly_trend} accessibilityLayer>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="month" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="count"
                      name="Resurse"
                      stroke="#2563eb"
                      strokeWidth={3}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </ChartPanel>
              <ChartPanel
                title="Workload pe departamente"
                description="Resurse atribuite fiecărei structuri."
                empty={!data.workload_by_department.length}
                table={
                  <DataTable
                    headers={["Departament", "Total"]}
                    rows={data.workload_by_department.map((row) => [
                      row.key,
                      row.count,
                    ])}
                  />
                }
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={data.workload_by_department}
                    layout="vertical"
                    accessibilityLayer
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} />
                    <YAxis type="category" dataKey="key" width={120} />
                    <Tooltip />
                    <Bar
                      dataKey="count"
                      name="Resurse"
                      fill="#0f766e"
                      radius={[0, 5, 5, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </ChartPanel>
              <ChartPanel
                title="Workload pe responsabili"
                description="Resursele atribuite individual, inclusiv cele nealocate."
                empty={!data.workload_by_responsible.length}
                table={
                  <DataTable
                    headers={["Responsabil", "Total"]}
                    rows={data.workload_by_responsible.map((row) => [
                      row.key,
                      row.count,
                    ])}
                  />
                }
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={data.workload_by_responsible}
                    layout="vertical"
                    accessibilityLayer
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} />
                    <YAxis type="category" dataKey="key" width={120} />
                    <Tooltip />
                    <Bar
                      dataKey="count"
                      name="Resurse"
                      fill="#d97706"
                      radius={[0, 5, 5, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </ChartPanel>
              <ChartPanel
                title={module === "contracts" ? "Contracte care expiră" : "Termene viitoare"}
                description="Intervale exclusive, fără dublarea elementelor între coloane."
                empty={!deadlineSeries.some((row) => row.count > 0)}
                table={
                  <DataTable
                    headers={["Interval", "Total"]}
                    rows={deadlineSeries.map((row) => [row.key, row.count])}
                  />
                }
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={deadlineSeries} accessibilityLayer>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="key" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="count" name="Total" fill="#0284c7" radius={[5, 5, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartPanel>
              <ChartPanel
                title="Indicatori operaționali"
                description={
                  module === "notifications"
                    ? `Livrări eșuate: ${Number(metrics.delivery_failure_rate ?? 0).toLocaleString("ro-RO")}%`
                    : "Indicatori calculați separat pentru tipurile relevante de resurse."
                }
                empty={!operationalSeries.some((row) => row.count > 0)}
                table={
                  <DataTable
                    headers={["Indicator", "Total"]}
                    rows={operationalSeries.map((row) => [row.key, row.count])}
                  />
                }
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={operationalSeries} layout="vertical" accessibilityLayer>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} />
                    <YAxis type="category" dataKey="key" width={145} />
                    <Tooltip />
                    <Bar dataKey="count" name="Total" fill="#475569" radius={[0, 5, 5, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartPanel>
              {(module === "legal" || !module) && (data.by_court?.length ?? 0) > 0 ? (
                <ChartPanel
                  title="Dosare pe instanță"
                  description="Distribuția dosarelor după instanța din metadatele controlate."
                  empty={false}
                  table={
                    <DataTable
                      headers={["Instanță", "Dosare"]}
                      rows={(data.by_court ?? []).map((row) => [row.key, row.count])}
                    />
                  }
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.by_court ?? []} layout="vertical" accessibilityLayer>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} />
                      <YAxis type="category" dataKey="key" width={145} />
                      <Tooltip />
                      <Bar dataKey="count" name="Dosare" fill="#7c3aed" radius={[0, 5, 5, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartPanel>
              ) : null}
              <ChartPanel
                title="Valori pe categorie și monedă"
                description="Fiecare categorie și monedă formează o serie distinctă."
                empty={!data.financial_exposure.length}
                table={
                  <DataTable
                    headers={["Categorie", "Monedă", "Valoare"]}
                    rows={data.financial_exposure.map((row) => [
                      row.category,
                      row.currency,
                      row.amount,
                    ])}
                  />
                }
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={financialSeries} accessibilityLayer>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="key" />
                    <YAxis />
                    <Tooltip />
                    <Bar
                      dataKey="amount"
                      name="Valoare"
                      fill="#7c3aed"
                      radius={[5, 5, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </ChartPanel>
            </section>
          )}
        </>
      ) : null}
    </>
  );
}
