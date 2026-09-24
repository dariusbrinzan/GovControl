"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import {
  Bell, BookOpenCheck, BriefcaseBusiness, CalendarClock, ChevronDown,
  CircleDollarSign, ClipboardCheck, FileCheck2, Files, Gavel, LayoutDashboard,
  Menu, PanelLeftClose, PanelLeftOpen, Search, Settings, ShieldCheck, UserRound,
  X,
} from "../ui/icons";
import { useSession } from "./session-provider";

const groups = [
  {
    label: "Activitate",
    items: [
      { href: "/legal", label: "Panou de control", icon: LayoutDashboard, exact: true, permission: "legal.report" },
      { href: "/legal/my-work", label: "Activitatea mea", icon: ClipboardCheck, permission: "legal.manage" },
    ],
  },
  {
    label: "Management juridic",
    items: [
      { href: "/legal/cases", label: "Dosare", icon: BriefcaseBusiness, permission: "legal.manage" },
      { href: "/legal/decisions", label: "Hotărâri", icon: Gavel, permission: "legal.manage" },
      { href: "/legal/obligations", label: "Obligații", icon: BookOpenCheck, permission: "legal.manage" },
      { href: "/legal/deadlines", label: "Termene critice", icon: CalendarClock, permission: "legal.manage" },
      { href: "/legal/enforcements", label: "Executări", icon: FileCheck2, permission: "legal.manage" },
      { href: "/legal/penalties", label: "Penalități", icon: CircleDollarSign, permission: "legal.manage" },
    ],
  },
  {
    label: "Evidență și control",
    items: [
      { href: "/legal/documents", label: "Documente", icon: Files, permission: "legal.manage" },
      { href: "/legal/notifications", label: "Notificări", icon: Bell, permission: "legal.manage" },
      { href: "/legal/audit", label: "Jurnal de audit", icon: ShieldCheck, permission: "audit.view" },
      { href: "/legal/reports", label: "Rapoarte", icon: FileCheck2, permission: "legal.report" },
    ],
  },
] as const;

const pageNames: Record<string, string> = {
  legal: "Panou de control", "my-work": "Activitatea mea", cases: "Dosare",
  decisions: "Hotărâri", obligations: "Obligații", deadlines: "Termene critice",
  enforcements: "Executări", penalties: "Penalități", documents: "Documente",
  notifications: "Notificări", audit: "Jurnal de audit", reports: "Rapoarte",
};

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, ready, error, connect, disconnect } = useSession();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showConnection, setShowConnection] = useState(false);
  const [draftToken, setDraftToken] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => setMobileOpen(false), [pathname]);
  const connectionVisible = showConnection || (ready && !user);

  const submitToken = async (event: FormEvent) => {
    event.preventDefault();
    setConnecting(true);
    try {
      await connect(draftToken);
      setDraftToken("");
      setShowConnection(false);
    } catch {
      // Error is exposed by the session provider.
    } finally {
      setConnecting(false);
    }
  };

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    if (query.trim().length >= 2) router.push(`/legal/search?q=${encodeURIComponent(query.trim())}`);
  };

  const parts = pathname.split("/").filter(Boolean);
  const currentName = pageNames[parts[1] ?? "legal"] ?? "Detalii";

  return (
    <div className={`portal-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <a className="skip-link" href="#main-content">Sari la conținut</a>
      <aside className={`portal-sidebar ${mobileOpen ? "mobile-open" : ""}`} aria-label="Navigare GovLegal">
        <div className="sidebar-brand">
          <span className="brand-mark" aria-hidden="true">GC</span>
          <div className="brand-copy"><strong>GovControl</strong><span>Platformă instituțională</span></div>
          <button className="icon-button mobile-only" onClick={() => setMobileOpen(false)} aria-label="Închide meniul"><X size={19} /></button>
        </div>
        <div className="module-card"><span className="module-icon"><Gavel size={18} /></span><div><small>Modul activ</small><strong>GovLegal</strong></div><ChevronDown size={15} /></div>
        <nav className="sidebar-nav" aria-label="Navigare GovLegal">
          {groups.map((group) => <div className="nav-group" key={group.label}>
            <p>{group.label}</p>
            {group.items.filter((item) => !user || user.permissions.includes(item.permission)).map(({ href, label, icon: Icon, ...item }) => {
              const active = "exact" in item && item.exact ? pathname === href : pathname.startsWith(href);
              return <Link aria-current={active ? "page" : undefined} className={active ? "active" : ""} href={href} key={href} title={collapsed ? label : undefined}><Icon size={18} strokeWidth={1.8} /><span>{label}</span></Link>;
            })}
          </div>)}
        </nav>
        <div className="sidebar-footer">
          <button onClick={() => setCollapsed((value) => !value)} type="button">
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}<span>Restrânge meniul</span>
          </button>
        </div>
      </aside>
      {mobileOpen ? <button className="sidebar-scrim" onClick={() => setMobileOpen(false)} aria-label="Închide meniul" /> : null}

      <div className="portal-main">
        <header className="portal-topbar">
          <button className="icon-button mobile-only" onClick={() => setMobileOpen(true)} aria-label="Deschide meniul"><Menu size={21} /></button>
          <nav className="breadcrumbs" aria-label="Breadcrumb"><Link href="/legal">GovLegal</Link><span>/</span><strong>{currentName}</strong></nav>
          <form className="global-search" onSubmit={submitSearch} role="search"><Search size={17} /><input aria-label="Caută în GovLegal" minLength={2} onChange={(event) => setQuery(event.target.value)} placeholder="Caută dosar, obligație…" value={query} /><kbd>⌘ K</kbd></form>
          <div className="topbar-actions">
            <Link className="icon-button" href="/legal/notifications" aria-label="Notificări"><Bell size={19} /></Link>
            <button className="profile-button" onClick={() => setShowConnection(true)} type="button"><span className="avatar"><UserRound size={17} /></span><span className="profile-copy"><strong>{user?.display_name ?? "Conectare"}</strong><small>{user?.roles[0]?.replaceAll("_", " ") ?? "Mediu local"}</small></span><ChevronDown size={15} /></button>
          </div>
        </header>
        <main id="main-content" className="portal-content" tabIndex={-1}>{children}</main>
      </div>

      {connectionVisible ? <div className="modal-backdrop" role="presentation"><section className="connection-modal" role="dialog" aria-modal="true" aria-labelledby="connection-title">
        {user ? <button className="modal-close icon-button" onClick={() => setShowConnection(false)} aria-label="Închide"><X size={18} /></button> : null}
        <span className="modal-icon"><Settings size={22} /></span>
        <p className="eyebrow">Conexiune securizată</p><h2 id="connection-title">{user ? "Sesiune locală activă" : "Conectează spațiul de lucru"}</h2>
        {user ? <><div className="session-summary"><strong>{user.display_name}</strong><span>{user.email}</span><small>{user.permissions.length} permisiuni active</small></div><div className="modal-actions"><button className="button secondary" onClick={() => setShowConnection(false)}>Continuă</button><button className="button danger-ghost" onClick={disconnect}>Deconectează</button></div></> : <form onSubmit={submitToken}><label htmlFor="session-token">DEV_AUTH_TOKEN</label><input autoFocus id="session-token" onChange={(event) => setDraftToken(event.target.value)} placeholder="Tokenul din fișierul .env" type="password" value={draftToken} /><p>Tokenul rămâne doar în browserul local și este trimis direct API-ului.</p>{error ? <div className="inline-error" role="alert">{error}</div> : null}<button className="button primary" disabled={connecting} type="submit">{connecting ? "Se verifică…" : "Conectează aplicația"}</button></form>}
      </section></div> : null}
    </div>
  );
}
