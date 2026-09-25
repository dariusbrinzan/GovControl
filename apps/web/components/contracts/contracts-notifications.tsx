"use client";

import { useCallback, useEffect, useState } from "react";

import {
  contractsGet,
  contractsPatch,
  type ContractNotification,
} from "../../lib/contracts";
import { formatDate } from "../../lib/legal";
import { Bell } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { useSession } from "../legal/session-provider";

export function ContractsNotifications() {
  const { token, ready } = useSession();
  const [items, setItems] = useState<ContractNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true); setError(null);
    try { setItems(await contractsGet<ContractNotification[]>("/contracts/notifications", token)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Notificările nu au putut fi încărcate."); }
    finally { setLoading(false); }
  }, [token]);
  useEffect(() => { void load(); }, [load]);
  const markRead = async (id: string) => {
    setUpdating(id); setError(null);
    try { await contractsPatch(`/contracts/notifications/${id}/read`, token, {}); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Notificarea nu a putut fi actualizată."); }
    finally { setUpdating(null); }
  };
  return <>
    <PageHeader eyebrow="Monitorizare automată" title="Notificări contractuale" description="Alerte idempotente generate de worker pentru jaloane, obligații și plăți apropiate." />
    {!ready || loading ? <LoadingState /> : null}
    {error ? <ErrorState message={error} retry={() => void load()} /> : null}
    {ready && !loading && !error && !items.length ? <EmptyState title="Nu există notificări" description="Workerul va crea automat alerte când un termen intră în orizontul de 14 zile." icon={<Bell size={25} />} /> : null}
    {items.length ? <section className="data-panel notifications-panel"><ul className="notification-list">{items.map((item) => <li className={item.read_at ? "" : "unread"} key={item.id}><div><strong>{item.title}</strong><p>{item.body}</p><span>{item.entity_type} · termen {formatDate(item.due_date)}</span></div>{item.read_at ? <span>Citită {formatDate(item.read_at)}</span> : <button disabled={updating === item.id} onClick={() => void markRead(item.id)}>Marchează citită</button>}</li>)}</ul></section> : null}
  </>;
}
