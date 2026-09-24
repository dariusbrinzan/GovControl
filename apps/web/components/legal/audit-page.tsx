"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, type AuditEventPage } from "../../lib/api";
import { downloadCsv, formatDate } from "../../lib/legal";
import { ShieldCheck } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { useSession } from "./session-provider";

export default function AuditPage() {
  const { token, user, ready } = useSession();
  const [page, setPage] = useState<AuditEventPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const load = useCallback(async () => {
    if (!token || !user?.permissions.includes("audit.view")) return;
    setLoading(true); setError(null);
    try { setPage(await apiGet<AuditEventPage>(`/audit/events?limit=25&offset=${offset}`, token)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Jurnalul nu poate fi încărcat."); }
    finally { setLoading(false); }
  }, [offset, token, user]);
  useEffect(() => { void load(); }, [load]);
  const items = page?.items ?? [];
  return <><PageHeader eyebrow="Trasabilitate instituțională" title="Jurnal de audit" description="Istoricul imuabil al operațiunilor efectuate în tenantul curent." actions={<button className="button secondary" disabled={!items.length} onClick={() => downloadCsv("govlegal-audit.csv", [["Acțiune", "Entitate", "ID", "Data"], ...items.map((item) => [item.action, item.entity_type, item.entity_id, item.created_at])])}>Exportă CSV</button>} />
    {!ready || loading ? <LoadingState /> : null}{error ? <ErrorState message={error} retry={() => void load()} /> : null}{user && !user.permissions.includes("audit.view") ? <ErrorState message="Rolul curent nu are permisiunea audit.view." /> : null}
    {items.length ? <section className="data-panel"><div className="table-wrap"><table><thead><tr><th>Moment</th><th>Acțiune</th><th>Tip entitate</th><th>Identificator</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{formatDate(item.created_at)}<small>{new Date(item.created_at).toLocaleTimeString("ro-RO", { hour: "2-digit", minute: "2-digit" })}</small></td><td><strong>{item.action.replaceAll("_", " ")}</strong></td><td>{item.entity_type}</td><td className="mono">{item.entity_id}</td></tr>)}</tbody></table></div><footer className="pagination"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Anterior</button><span>Înregistrările {offset + 1}–{offset + items.length}</span><button disabled={items.length < 25} onClick={() => setOffset(offset + 25)}>Următor</button></footer></section> : ready && user && !loading && !error ? <EmptyState title="Jurnalul este gol" description="Evenimentele vor apărea după primele operațiuni." icon={<ShieldCheck size={26} />} /> : null}</>;
}
