"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiGet, type LegalSearchResponse, type LegalSearchResult } from "../../lib/api";
import { formatDate } from "../../lib/legal";
import { Search } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { StatusBadge } from "../ui/status-badge";
import { useSession } from "./session-provider";

export default function SearchPage() {
  const params = useSearchParams(); const initial = params.get("q") ?? "";
  const { token } = useSession(); const [query, setQuery] = useState(initial); const [results, setResults] = useState<LegalSearchResult[]>([]); const [loading, setLoading] = useState(false); const [error, setError] = useState<string | null>(null); const [searched, setSearched] = useState(false);
  const search = useCallback(async (term: string) => { if (!token || term.trim().length < 2) return; setLoading(true); setError(null); try { const response = await apiGet<LegalSearchResponse>(`/search/legal?q=${encodeURIComponent(term.trim())}`, token); setResults(response.results); setSearched(true); } catch (reason) { setError(reason instanceof Error ? reason.message : "Căutarea nu a reușit."); } finally { setLoading(false); } }, [token]);
  useEffect(() => { if (initial) void search(initial); }, [initial, search]);
  return <><PageHeader eyebrow="Căutare globală" title="Rezultate GovLegal" description="Caută transversal în dosare și obligații, fără a pierde contextul instituției." /><form className="search-page-form" onSubmit={(event) => { event.preventDefault(); void search(query); }}><Search size={20} /><input autoFocus minLength={2} onChange={(event) => setQuery(event.target.value)} placeholder="Număr dosar sau text din obligație" value={query} /><button className="button primary">Caută</button></form>{loading ? <LoadingState label="Căutăm în registrul juridic…" /> : null}{error ? <ErrorState message={error} /> : null}{results.length ? <section className="search-results">{results.map((item) => <Link className="search-result-card" href={item.entity_type === "LegalCase" ? `/legal/cases/${item.id}` : `/legal/obligations/${item.id}`} key={`${item.entity_type}-${item.id}`}><div><small>{item.entity_type === "LegalCase" ? "Dosar" : "Obligație"}</small><h2>{item.title}</h2><p>{item.summary}</p></div><div className="result-meta"><StatusBadge status={item.status} /><span>{formatDate(item.due_date)}</span></div></Link>)}</section> : searched && !loading ? <EmptyState title="Niciun rezultat" description="Încearcă numărul dosarului sau un fragment mai scurt din descriere." icon={<Search size={26} />} /> : null}</>;
}
