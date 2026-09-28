"use client";

import { useCallback, useEffect, useState } from "react";

import {
  exportDownloadUrl,
  insightsGet,
  type ExportArtifact,
} from "../../lib/insights";
import { Files } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { useSession } from "../legal/session-provider";

export function ExportsHistory() {
  const { user } = useSession();
  const [items, setItems] = useState<ExportArtifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const allowed = user?.permissions.includes("insights.export") ?? false;
  const load = useCallback(async () => {
    if (!allowed) return;
    setLoading(true);
    setError(null);
    try {
      setItems(await insightsGet<ExportArtifact[]>("/exports"));
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Exporturile nu sunt disponibile.",
      );
    } finally {
      setLoading(false);
    }
  }, [allowed]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (
      !items.some(
        (item) => item.status === "QUEUED" || item.status === "RUNNING",
      )
    )
      return;
    const timer = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(timer);
  }, [items, load]);
  return (
    <>
      <PageHeader
        eyebrow="GovInsights · livrare securizată"
        title="Istoric exporturi"
        description="Fișierele sunt generate asincron, autorizate la descărcare și eliminate după expirare."
        actions={
          <button className="button secondary" onClick={() => void load()}>
            Actualizează
          </button>
        }
      />
      {user && !allowed ? (
        <ErrorState message="Rolul curent nu are permisiunea insights.export." />
      ) : null}
      {loading && !items.length ? (
        <LoadingState label="Verificăm joburile de export…" />
      ) : null}
      {error ? <ErrorState message={error} retry={() => void load()} /> : null}
      {allowed && !loading && !items.length ? (
        <EmptyState
          title="Nu există exporturi"
          description="Pornește un export CSV sau XLSX din pagina Rapoarte."
          icon={<Files size={25} />}
        />
      ) : null}
      {items.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Creat</th>
                <th>Format</th>
                <th>Status</th>
                <th>Dimensiune</th>
                <th>Expiră</th>
                <th>Acțiune</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{new Date(item.created_at).toLocaleString("ro-RO")}</td>
                  <td>{item.format.toUpperCase()}</td>
                  <td>
                    <span
                      className={`status-badge ${item.status.toLowerCase()}`}
                    >
                      {item.status}
                    </span>
                  </td>
                  <td>
                    {item.size_bytes
                      ? `${Math.ceil(item.size_bytes / 1024)} KB`
                      : "—"}
                  </td>
                  <td>{new Date(item.expires_at).toLocaleString("ro-RO")}</td>
                  <td>
                    {item.status === "SUCCEEDED" ? (
                      <a
                        className="button secondary"
                        href={exportDownloadUrl(item.id)}
                      >
                        Descarcă
                      </a>
                    ) : (
                      "În procesare"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}
