"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { insightsGet, type InsightsSearchPage } from "../../lib/insights";
import { Search } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { useSession } from "../legal/session-provider";

export function InsightsSearchView() {
  const params = useSearchParams();
  const router = useRouter();
  const { user } = useSession();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [module, setModule] = useState(params.get("module") ?? "");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [data, setData] = useState<InsightsSearchPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const current = params.get("q")?.trim() ?? "";
    const hasFilter = [
      "module",
      "resource_type",
      "status",
      "responsible_user_id",
      "date_from",
      "date_to",
    ].some((key) => params.has(key));
    if (
      (current.length > 0 && current.length < 2) ||
      (!current && !hasFilter) ||
      !user?.permissions.includes("insights.search")
    )
      return;
    setLoading(true);
    setError(null);
    try {
      setData(
        await insightsGet<InsightsSearchPage>(`/search?${params.toString()}`),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Căutarea nu este disponibilă.",
      );
    } finally {
      setLoading(false);
    }
  }, [params, user]);
  useEffect(() => {
    void load();
  }, [load]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (query.trim().length === 1 || (!query.trim() && !module && !status)) return;
    const next = new URLSearchParams();
    if (query.trim()) next.set("q", query.trim());
    if (module) next.set("module", module);
    if (status) next.set("status", status);
    next.set("limit", "25");
    router.push(`/insights/search?${next}`);
  };
  const navigateOffset = (offset: number) => {
    const next = new URLSearchParams(params);
    next.set("offset", String(Math.max(0, offset)));
    router.push(`/insights/search?${next}`);
  };
  return (
    <>
      <PageHeader
        eyebrow="GovInsights · căutare federată"
        title="Căutare unificată"
        description="Caută identificatori și metadate controlate din toate modulele, strict în instituția curentă."
      />
      <form className="insights-search-form" onSubmit={submit}>
        <Search size={19} />
        <input
          aria-label="Termen de căutare"
          minLength={2}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Număr dosar, contract, document…"
        />
        <select
          aria-label="Modul"
          value={module}
          onChange={(event) => setModule(event.target.value)}
        >
          <option value="">Toate modulele</option>
          <option value="legal">GovLegal</option>
          <option value="contracts">GovContracts</option>
          <option value="documents">GovDocuments</option>
          <option value="notifications">GovNotifications</option>
        </select>
        <input
          aria-label="Status"
          value={status}
          onChange={(event) => setStatus(event.target.value.toUpperCase())}
          placeholder="Status (opțional)"
        />
        <button className="button primary" type="submit">
          Caută
        </button>
      </form>
      {user && !user.permissions.includes("insights.search") ? (
        <ErrorState message="Rolul curent nu are permisiunea insights.search." />
      ) : null}
      {loading ? (
        <LoadingState label="Căutăm în proiecțiile GovInsights…" />
      ) : null}
      {error ? <ErrorState message={error} retry={() => void load()} /> : null}
      {data && !loading ? (
        <section className="search-results" aria-live="polite">
          <div className="result-count">
            <strong>{data.total}</strong> rezultate tenant-scoped
          </div>
          {data.items.length ? (
            <>
              {data.items.map((item) => (
                <Link
                  className="search-result-card"
                  href={item.source_url}
                  key={item.id}
                >
                  <div>
                    <span className="result-module">{item.module}</span>
                    <h2>
                      {item.identifier ??
                        item.display_label ??
                        item.resource_type}
                    </h2>
                    <p>{item.display_label ?? "Metadată controlată"}</p>
                  </div>
                  <div className="result-meta">
                    <span>{item.resource_type}</span>
                    <strong>{item.status ?? "Fără status"}</strong>
                  </div>
                </Link>
              ))}
              <nav className="pagination" aria-label="Paginare rezultate">
                <button
                  className="button ghost"
                  type="button"
                  disabled={data.offset === 0}
                  onClick={() => navigateOffset(data.offset - data.limit)}
                >
                  Pagina anterioară
                </button>
                <span>
                  {data.offset + 1}–{Math.min(data.offset + data.limit, data.total)} din {data.total}
                </span>
                <button
                  className="button ghost"
                  type="button"
                  disabled={data.offset + data.limit >= data.total}
                  onClick={() => navigateOffset(data.offset + data.limit)}
                >
                  Pagina următoare
                </button>
              </nav>
            </>
          ) : (
            <EmptyState
              title="Nu am găsit rezultate"
              description="Verifică identificatorul sau elimină filtrul de modul."
              icon={<Search size={25} />}
            />
          )}
        </section>
      ) : null}
    </>
  );
}
