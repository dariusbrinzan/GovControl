import { statusLabel } from "../../lib/legal";

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${status.toLowerCase()}`}>{statusLabel(status)}</span>;
}
