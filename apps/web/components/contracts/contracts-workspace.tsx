"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";

import {
  contractsGet,
  contractsPatch,
  contractsPost,
  type ContractDashboard,
  type ContractPage,
  type ContractRecord,
  type ContractStatus,
} from "../../lib/contracts";
import { downloadCsv, formatDate } from "../../lib/legal";
import { BriefcaseBusiness, FileClock } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { StatusBadge } from "../ui/status-badge";
import { useSession } from "../legal/session-provider";

const transitions: Record<ContractStatus, ContractStatus[]> = {
  DRAFT: ["IN_REVIEW", "CANCELLED"],
  IN_REVIEW: ["DRAFT", "ACTIVE", "CANCELLED"],
  ACTIVE: ["SUSPENDED", "COMPLETED", "TERMINATED"],
  SUSPENDED: ["ACTIVE", "TERMINATED"],
  COMPLETED: [], TERMINATED: [], CANCELLED: [],
};

const money = new Intl.NumberFormat("ro-RO", { maximumFractionDigits: 2 });

export function ContractsWorkspace({ view }: { view: "dashboard" | "registry" }) {
  const { token, user, ready } = useSession();
  const [items, setItems] = useState<ContractRecord[]>([]);
  const [dashboard, setDashboard] = useState<ContractDashboard | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [updating, setUpdating] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const pageSize = 10;

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true); setError(null);
    try {
      if (view === "registry") {
        const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
        if (query.trim()) params.set("search", query.trim());
        if (statusFilter) params.set("status", statusFilter);
        const page = await contractsGet<ContractPage>(`/contracts/page?${params}`, token);
        setItems(page.items); setTotal(page.total);
      } else {
        const metrics = await contractsGet<ContractDashboard>("/contracts/dashboard", token);
        setItems([]); setTotal(metrics.total_contracts); setDashboard(metrics);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Datele contractuale nu au putut fi încărcate.");
    } finally { setLoading(false); }
  }, [offset, query, statusFilter, token, view]);

  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => view === "registry" ? items : items.filter((item) => {
    const text = `${item.contract_number} ${item.title} ${item.description ?? ""}`.toLocaleLowerCase("ro");
    return (!query || text.includes(query.toLocaleLowerCase("ro"))) &&
      (!statusFilter || item.status === statusFilter);
  }), [items, query, statusFilter, view]);
  const statusCounts = dashboard?.status_counts ?? {};
  const activeValues = dashboard
    ? Object.entries(dashboard.active_value_by_currency)
        .map(([currency, value]) => `${money.format(Number(value))} ${currency}`)
        .join(" · ")
    : "";

  const changeStatus = async (item: ContractRecord, status: ContractStatus) => {
    setUpdating(item.id); setError(null);
    try { await contractsPatch(`/contracts/${item.id}/status`, token, { status }); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Statusul nu a putut fi actualizat."); }
    finally { setUpdating(null); }
  };
  const exportCsv = () => downloadCsv("govcontracts-register.csv", [
    ["Număr", "Titlu", "Valoare", "Monedă", "Început", "Sfârșit", "Status"],
    ...filtered.map((item) => [item.contract_number, item.title, item.value, item.currency, item.start_date, item.end_date, item.status]),
  ]);

  const createAction = token ? <CreateContractForm token={token} onCreated={load} /> : null;
  const content = view === "dashboard" ? <>
    <PageHeader eyebrow="Management contractual" title="Controlul contractelor instituției" description="Valori, stări și scadențe monitorizate separat de GovLegal, într-un serviciu dedicat." actions={createAction} />
    {dashboard ? <section className="metric-grid" aria-label="Indicatori contractuali">
      <article><span>Total contracte</span><strong>{dashboard.total_contracts}</strong><small>în registrul instituției</small></article>
      <article><span>Contracte active</span><strong>{dashboard.active_contracts}</strong><small>aflate în execuție</small></article>
      <article className={dashboard.expiring_within_30_days ? "danger" : ""}><span>Expiră în 30 zile</span><strong>{dashboard.expiring_within_30_days}</strong><small>necesită analiză</small></article>
      <article><span>Valoare activă</span><strong>{activeValues || "0"}</strong><small>separată corect pe monede</small></article>
    </section> : null}
    {dashboard && dashboard.total_contracts ? <section className="content-grid"><article className="data-panel panel"><div className="panel-heading"><div><h2>Distribuția pe stări</h2><p>Imagine operațională a întregului portofoliu contractual.</p></div></div><div className="status-chart" role="img" aria-label="Distribuția contractelor după status">{Object.entries(statusCounts).map(([status, count]) => <div key={status}><span>{status.replaceAll("_", " ")}</span><div><i style={{ width: `${Math.max(8, ((count ?? 0) / dashboard.total_contracts) * 100)}%` }} /></div><strong>{count}</strong></div>)}</div></article><aside className="side-column"><article className="panel data-panel"><FileClock size={22} /><h2>Execuție monitorizată</h2><p>Jaloanele, plățile și obligațiile alimentează alertele operaționale.</p></article></aside></section> : null}
  </> : <>
    <PageHeader eyebrow="Evidență centralizată" title="Registrul contractelor" description="Filtrează, exportă și actualizează contractele instituției." actions={<><button className="button secondary" disabled={!filtered.length} onClick={exportCsv}>Exportă CSV</button>{createAction}</>} />
    <section className="list-toolbar" aria-label="Filtre registru"><label className="search-field"><span className="sr-only">Caută în registru</span><input onChange={(event) => { setQuery(event.target.value); setOffset(0); }} placeholder="Număr, titlu sau descriere…" value={query} /></label><label><span className="sr-only">Filtrează după status</span><select onChange={(event) => { setStatusFilter(event.target.value); setOffset(0); }} value={statusFilter}><option value="">Toate statusurile</option>{Object.keys(transitions).map((status) => <option key={status}>{status}</option>)}</select></label><span className="result-count">{total} rezultate</span></section>
    {filtered.length ? <section className="data-panel"><div className="table-wrap"><table className="resource-table"><thead><tr><th>Contract</th><th>Valoare</th><th>Perioadă</th><th>Status</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.id}><td><Link className="primary-cell" href={`/contracts/${item.id}`}>{item.contract_number}</Link><small>{item.title}</small></td><td><strong>{money.format(Number(item.value))} {item.currency}</strong></td><td>{formatDate(item.start_date)} – {formatDate(item.end_date)}</td><td><StatusBadge status={item.status} />{transitions[item.status].length ? <select aria-label={`Actualizează ${item.contract_number}`} className="inline-status-select" defaultValue="" disabled={updating === item.id} onChange={(event) => { if (event.target.value) void changeStatus(item, event.target.value as ContractStatus); }}><option value="">Actualizează…</option>{transitions[item.status].map((status) => <option key={status}>{status}</option>)}</select> : null}</td></tr>)}</tbody></table></div></section> : null}
    {total > pageSize ? <nav className="pagination" aria-label="Paginare registru"><button className="button secondary" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Pagina anterioară</button><span>{offset + 1}–{Math.min(offset + pageSize, total)} din {total}</span><button className="button secondary" disabled={offset + pageSize >= total || loading} onClick={() => setOffset(offset + pageSize)}>Pagina următoare</button></nav> : null}
    {!total ? <EmptyState title="Niciun contract găsit" description={query || statusFilter ? "Modifică filtrele aplicate registrului." : "Adaugă primul contract pentru a activa registrul."} icon={<BriefcaseBusiness size={26} />} /> : null}
  </>;

  if (!ready || loading) return <LoadingState />;
  if (error) return <><ErrorState message={error} retry={() => void load()} />{content}</>;
  if (view === "dashboard" && user && dashboard?.total_contracts === 0) return <><PageHeader eyebrow="Management contractual" title="GovContracts" description="Registrul contractual al instituției este pregătit." actions={createAction} /><EmptyState title="Nu există încă contracte" description="Adaugă primul contract pentru a activa indicatorii și monitorizarea." icon={<BriefcaseBusiness size={26} />} /></>;
  return content;
}

function CreateContractForm({ token, onCreated }: { token: string; onCreated: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true); setError(null);
    try {
      await contractsPost("/contracts", token, Object.fromEntries(form.entries()));
      setOpen(false); await onCreated();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Contractul nu a putut fi creat."); }
    finally { setSaving(false); }
  };
  return <><button className="button primary" onClick={() => setOpen(true)} type="button">Adaugă contract</button>{open ? <div className="modal-backdrop" role="presentation"><section className="connection-modal contract-modal" role="dialog" aria-modal="true" aria-labelledby="contract-create-title"><p className="eyebrow">GovContracts</p><h2 id="contract-create-title">Contract nou</h2><form className="case-form" onSubmit={submit}><label>Număr<input name="contract_number" required /></label><label className="wide">Titlu<input name="title" required /></label><label>Valoare<input min="0.01" name="value" required step="0.01" type="number" /></label><label>Monedă<input defaultValue="RON" maxLength={3} name="currency" required /></label><label>Data semnării<input name="signed_date" type="date" /></label><label>Început<input name="start_date" required type="date" /></label><label>Sfârșit<input name="end_date" required type="date" /></label><label className="wide">Descriere<textarea name="description" rows={3} /></label>{error ? <div className="inline-error wide" role="alert">{error}</div> : null}<div className="modal-actions wide"><button className="button secondary" onClick={() => setOpen(false)} type="button">Renunță</button><button className="button primary" disabled={saving} type="submit">{saving ? "Se salvează…" : "Salvează"}</button></div></form></section></div> : null}</>;
}
