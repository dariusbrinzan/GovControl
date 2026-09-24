import type { ReactNode } from "react";

export function LoadingState({ label = "Se încarcă datele…" }: { label?: string }) {
  return <div className="data-state" role="status"><span className="spinner" aria-hidden="true" /><strong>{label}</strong></div>;
}

export function EmptyState({ title, description, icon }: { title: string; description: string; icon?: ReactNode }) {
  return <div className="empty-state-card">{icon}<strong>{title}</strong><p>{description}</p></div>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="alert alert-error" role="alert"><div><strong>Date indisponibile</strong><p>{message}</p></div>{retry ? <button onClick={retry} type="button">Reîncearcă</button> : null}</div>;
}
