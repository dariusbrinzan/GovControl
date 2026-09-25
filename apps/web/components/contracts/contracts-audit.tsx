"use client";

import { useCallback, useEffect, useState } from "react";

import { contractsGet, type ContractAuditPage } from "../../lib/contracts";
import { formatDate } from "../../lib/legal";
import { ShieldCheck } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { useSession } from "../legal/session-provider";

export function ContractsAudit() {
  const { token, ready } = useSession();
  const [page, setPage] = useState<ContractAuditPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const limit = 20;
  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true); setError(null);
    try { setPage(await contractsGet<ContractAuditPage>(`/contracts/audit?limit=${limit}&offset=${offset}`, token)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Auditul nu a putut fi încărcat."); }
    finally { setLoading(false); }
  }, [offset, token]);
  useEffect(() => { void load(); }, [load]);
  return <>
    <PageHeader eyebrow="Trasabilitate" title="Jurnal audit GovContracts" description="Evenimente append-only pentru operațiile contractuale critice, izolate pe instituție." />
    {!ready || loading ? <LoadingState /> : null}
    {error ? <ErrorState message={error} retry={() => void load()} /> : null}
    {page && !page.items.length ? <EmptyState title="Nu există evenimente" description="Evenimentele vor apărea după prima operație contractuală." icon={<ShieldCheck size={25} />} /> : null}
    {page?.items.length ? <section className="data-panel"><div className="table-wrap"><table className="resource-table"><thead><tr><th>Acțiune</th><th>Entitate</th><th>Actor</th><th>Request ID</th><th>Moment</th></tr></thead><tbody>{page.items.map((item) => <tr key={item.id}><td><strong>{item.action.replaceAll("_", " ")}</strong><small>{item.payload ? JSON.stringify(item.payload) : "Fără payload"}</small></td><td>{item.entity_type}<small>{item.entity_id}</small></td><td className="mono">{item.actor_user_id}</td><td className="mono">{item.request_id ?? "—"}</td><td>{formatDate(item.created_at)}</td></tr>)}</tbody></table></div></section> : null}
    {page && page.total > limit ? <nav className="pagination" aria-label="Paginare audit"><button className="button secondary" disabled={!offset || loading} onClick={() => setOffset(Math.max(0, offset - limit))}>Pagina anterioară</button><span>{offset + 1}–{Math.min(offset + limit, page.total)} din {page.total}</span><button className="button secondary" disabled={offset + limit >= page.total || loading} onClick={() => setOffset(offset + limit)}>Pagina următoare</button></nav> : null}
  </>;
}
