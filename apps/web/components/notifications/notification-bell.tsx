"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { notificationsGet, type NotificationPage } from "../../lib/notifications";
import { useSession } from "../legal/session-provider";
import { Bell } from "../ui/icons";

export function NotificationBell({ href }: { href: string }) {
  const { user } = useSession();
  const [count, setCount] = useState(0);
  const [recent, setRecent] = useState<NotificationPage["items"]>([]);
  const [open, setOpen] = useState(false);
  const canRead = user?.permissions.includes("notifications.read") ?? false;
  const load = useCallback(async () => {
    if (!canRead) return;
    try {
      const [unread, page] = await Promise.all([
        notificationsGet<{ count: number }>("/unread-count"),
        notificationsGet<NotificationPage>("?limit=5&offset=0"),
      ]);
      setCount(unread.count); setRecent(page.items);
    } catch { setCount(0); setRecent([]); }
  }, [canRead]);

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 60_000);
    return () => window.clearInterval(interval);
  }, [load]);

  if (!canRead) return null;
  return <div className="notification-bell"><button className="icon-button" aria-expanded={open} aria-label={`Notificări necitite: ${count}`} onClick={() => setOpen((value) => !value)} type="button"><Bell size={19} />{count ? <span className="notification-badge">{count > 99 ? "99+" : count}</span> : null}</button>{open ? <section className="notification-popover"><div><strong>Notificări recente</strong><span>{count} necitite</span></div>{recent.length ? <ul>{recent.map((item) => <li key={item.id}><Link href={item.resource_url ?? href} onClick={() => setOpen(false)}><strong>{item.title}</strong><span>{item.category} · {item.status}</span></Link></li>)}</ul> : <p>Nu există notificări sau serviciul este temporar indisponibil.</p>}<Link className="popover-footer" href={href} onClick={() => setOpen(false)}>Deschide centrul de notificări</Link></section> : null}</div>;
}
