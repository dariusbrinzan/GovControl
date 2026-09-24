"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, type LegalAnalytics } from "../../lib/api";
import { downloadCsv, formatCurrency } from "../../lib/legal";
import { FileCheck2 } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { useSession } from "./session-provider";

export default function ReportsPage() {
  const { token, user, ready } = useSession();
  const [data, setData] = useState<LegalAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { if (!token || !user?.permissions.includes("legal.report")) return; try { setData(await apiGet<LegalAnalytics>("/legal/analytics/dashboard", token)); } catch (reason) { setError(reason instanceof Error ? reason.message : "Raportul nu poate fi generat."); } }, [token, user]);
  useEffect(() => { void load(); }, [load]);
  const rows: Array<[string, string | number, string]> = data ? [
    ["Obligații active", data.kpis.active_obligations, "număr"], ["Termene depășite", data.kpis.overdue_obligations, "număr"], ["Scadente în 7 zile", data.kpis.due_within_seven_days, "număr"], ["Executări active", data.kpis.active_enforcements, "număr"], ["Expunere financiară", formatCurrency(data.kpis.financial_exposure), "estimare"], ["Rată finalizare", `${data.kpis.completion_rate}%`, "procent"],
  ] : [];
  return <><PageHeader eyebrow="Raportare managerială" title="Rapoarte și indicatori" description="Sinteză pregătită pentru analiză, ședințe de management și export." actions={<button className="button primary" disabled={!data} onClick={() => downloadCsv(`raport-govlegal-${data?.generated_on}.csv`, [["Indicator", "Valoare", "Unitate"], ...rows])}>Descarcă raportul</button>} />
    {!ready ? <LoadingState /> : null}{error ? <ErrorState message={error} retry={() => void load()} /> : null}{data ? <section className="report-layout"><article className="data-panel"><header className="panel-title"><h2>Sinteză executivă</h2><p>Perioada {data.filters.period.date_from} – {data.filters.period.date_to}</p></header><div className="table-wrap"><table><thead><tr><th>Indicator</th><th>Valoare</th><th>Tip</th></tr></thead><tbody>{rows.map((row) => <tr key={row[0]}><td><strong>{row[0]}</strong></td><td>{row[1]}</td><td>{row[2]}</td></tr>)}</tbody></table></div></article><aside className="report-note"><FileCheck2 size={28} /><h2>Raport verificabil</h2><p>Valorile sunt calculate din datele tenantului curent și respectă filtrele de perioadă din serviciul de analytics.</p><small>Generat la {data.generated_on}</small></aside></section> : ready && user && !error ? <EmptyState title="Raport indisponibil" description="Nu există date sau permisiunea de raportare nu este activă." icon={<FileCheck2 size={26} />} /> : null}</>;
}
