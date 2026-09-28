"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";

import {
  insightsDelete,
  insightsGet,
  insightsPost,
  type InsightsMetadata,
  type ReportRun,
  type SavedReport,
} from "../../lib/insights";
import { FileCheck2 } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { useSession } from "../legal/session-provider";

const labels: Record<string, string> = {
  module: "Modul",
  resource_type: "Tip resursă",
  identifier: "Identificator",
  display_label: "Denumire",
  status: "Status",
  department_id: "Departament",
  responsible_user_id: "Responsabil",
  occurred_at: "Data activității",
  due_at: "Termen",
  amount: "Valoare",
  currency: "Monedă",
};

export function ReportsWorkspace() {
  const { token, user } = useSession();
  const [metadata, setMetadata] = useState<InsightsMetadata | null>(null);
  const [reports, setReports] = useState<SavedReport[]>([]);
  const [runs, setRuns] = useState<ReportRun[]>([]);
  const [name, setName] = useState("");
  const [resourceType, setResourceType] = useState("contract");
  const [filterModule, setFilterModule] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortColumn, setSortColumn] = useState("occurred_at");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [sharedRoles, setSharedRoles] = useState("");
  const [columns, setColumns] = useState([
    "identifier",
    "display_label",
    "status",
    "due_at",
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allowed = user?.permissions.includes("insights.report") ?? false;
  const load = useCallback(async () => {
    if (!allowed) return;
    setLoading(true);
    setError(null);
    try {
      const [meta, saved, history] = await Promise.all([
        insightsGet<InsightsMetadata>("/metadata"),
        insightsGet<SavedReport[]>("/reports"),
        insightsGet<ReportRun[]>("/runs"),
      ]);
      setMetadata(meta);
      setReports(saved);
      setRuns(history);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Rapoartele nu sunt disponibile.",
      );
    } finally {
      setLoading(false);
    }
  }, [allowed]);
  useEffect(() => {
    void load();
  }, [load]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || !columns.length) return;
    setError(null);
    try {
      const filters = Object.fromEntries(
        Object.entries({
          module: filterModule,
          status: filterStatus.trim().toUpperCase(),
          date_from: dateFrom,
          date_to: dateTo,
        }).filter(([, value]) => value),
      );
      await insightsPost<SavedReport>("/reports", token, {
        name: name.trim(),
        description: null,
        resource_type: resourceType,
        filters,
        columns,
        sort: [{ column: sortColumn, direction: sortDirection }],
        shared_with_roles: sharedRoles
          .split(",")
          .map((role) => role.trim())
          .filter(Boolean),
      });
      setName("");
      await load();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Raportul nu a fost salvat.",
      );
    }
  };
  const run = async (reportId: string, format: "csv" | "xlsx" | null) => {
    try {
      await insightsPost<ReportRun>(`/reports/${reportId}/runs`, token, {
        export_format: format,
      });
      await load();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Rularea nu a fost pornită.",
      );
    }
  };
  const remove = async (reportId: string) => {
    try {
      await insightsDelete(`/reports/${reportId}`, token);
      await load();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Raportul nu a fost șters.",
      );
    }
  };
  const latestRun = useMemo(
    () => new Map(runs.map((item) => [item.report_id, item])),
    [runs],
  );

  return (
    <>
      <PageHeader
        eyebrow="GovInsights · raportare controlată"
        title="Constructor de rapoarte"
        description="Selectează numai dimensiuni aprobate. Interogările SQL arbitrare nu sunt acceptate."
      />
      {!allowed && user ? (
        <ErrorState message="Rolul curent nu are permisiunea insights.report." />
      ) : null}
      {loading ? (
        <LoadingState label="Încărcăm definițiile și istoricul…" />
      ) : null}
      {error ? <ErrorState message={error} retry={() => void load()} /> : null}
      {allowed ? (
        <div className="report-layout">
          <form className="report-builder" onSubmit={submit}>
            <div className="panel-title">
              <h2>Raport nou</h2>
              <p>Definiția este salvată și izolată în tenantul curent.</p>
            </div>
            <label>
              Nume raport
              <input
                required
                maxLength={200}
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Ex. Contracte care expiră"
              />
            </label>
            <label>
              Tip resursă
              <select
                value={resourceType}
                onChange={(event) => setResourceType(event.target.value)}
              >
                {(metadata?.report_resource_types ?? ["contract"]).map((item) => (
                  <option value={item} key={item}>
                    {labels[item] ?? item}
                  </option>
                ))}
              </select>
            </label>
            <div className="report-filter-grid">
              <label>
                Modul
                <select
                  value={filterModule}
                  onChange={(event) => setFilterModule(event.target.value)}
                >
                  <option value="">Toate modulele</option>
                  {metadata?.modules.map((item) => (
                    <option value={item} key={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Status
                <input
                  maxLength={80}
                  value={filterStatus}
                  onChange={(event) => setFilterStatus(event.target.value)}
                  placeholder="Ex. ACTIVE"
                />
              </label>
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
                  min={dateFrom || undefined}
                  value={dateTo}
                  onChange={(event) => setDateTo(event.target.value)}
                />
              </label>
              <label>
                Sortează după
                <select
                  value={sortColumn}
                  onChange={(event) => setSortColumn(event.target.value)}
                >
                  {metadata?.report_columns.map((column) => (
                    <option value={column} key={column}>
                      {labels[column] ?? column}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Direcție
                <select
                  value={sortDirection}
                  onChange={(event) =>
                    setSortDirection(event.target.value as "asc" | "desc")
                  }
                >
                  <option value="desc">Descrescător</option>
                  <option value="asc">Crescător</option>
                </select>
              </label>
            </div>
            <label>
              Partajare cu roluri
              <input
                maxLength={300}
                value={sharedRoles}
                onChange={(event) => setSharedRoles(event.target.value)}
                placeholder="auditor, legal_director"
              />
              <small>Roluri separate prin virgulă; raportul rămâne tenant-scoped.</small>
            </label>
            <fieldset>
              <legend>Coloane incluse</legend>
              <div className="column-picker">
                {metadata?.report_columns.map((column) => (
                  <label key={column}>
                    <input
                      type="checkbox"
                      checked={columns.includes(column)}
                      onChange={() =>
                        setColumns((current) =>
                          current.includes(column)
                            ? current.filter((item) => item !== column)
                            : [...current, column],
                        )
                      }
                    />
                    {labels[column] ?? column}
                  </label>
                ))}
              </div>
            </fieldset>
            <button
              className="button primary"
              disabled={!columns.length}
              type="submit"
            >
              Salvează raportul
            </button>
          </form>
          <section className="saved-reports">
            <div className="panel-title">
              <h2>Rapoarte salvate</h2>
              <p>{reports.length} definiții disponibile</p>
            </div>
            {reports.length ? (
              reports.map((report) => {
                const history = latestRun.get(report.id);
                return (
                  <article className="saved-report-card" key={report.id}>
                    <div>
                      <span>{report.resource_type}</span>
                      <h3>{report.name}</h3>
                      <p>
                        {report.columns
                          .map((column) => labels[column] ?? column)
                          .join(" · ")}
                      </p>
                      {history ? (
                        <small>
                          Ultima rulare: {history.status} ·{" "}
                          {new Date(history.requested_at).toLocaleString(
                            "ro-RO",
                          )}
                        </small>
                      ) : (
                        <small>Nu a fost rulat încă</small>
                      )}
                    </div>
                    <div className="report-actions">
                      <button
                        className="button ghost"
                        onClick={() => void run(report.id, null)}
                      >
                        Rulează
                      </button>
                      {user?.permissions.includes("insights.export") ? (
                        <>
                          <button
                            className="button secondary"
                            onClick={() => void run(report.id, "csv")}
                          >
                            CSV
                          </button>
                          <button
                            className="button secondary"
                            onClick={() => void run(report.id, "xlsx")}
                          >
                            XLSX
                          </button>
                        </>
                      ) : null}
                      <button
                        className="button danger-ghost"
                        onClick={() => void remove(report.id)}
                      >
                        Șterge
                      </button>
                    </div>
                  </article>
                );
              })
            ) : (
              <EmptyState
                title="Nu există rapoarte salvate"
                description="Creează prima definiție folosind constructorul controlat."
                icon={<FileCheck2 size={25} />}
              />
            )}
          </section>
        </div>
      ) : null}
    </>
  );
}
