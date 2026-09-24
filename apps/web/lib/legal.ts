import type { LegalObligation } from "./api";

export const statusLabels: Record<string, string> = {
  DRAFT: "Ciornă",
  OPEN: "Deschisă",
  IN_PROGRESS: "În lucru",
  AT_RISK: "La risc",
  OVERDUE: "Depășită",
  COMPLETED: "Finalizată",
  CANCELLED: "Anulată",
  SUSPENDED: "Suspendată",
  CLOSED: "Închisă",
  UNREAD: "Necitită",
  READ: "Citită",
};

export const obligationTypeLabels: Record<string, string> = {
  DO: "Executare",
  PAY: "Plată",
  REFRAIN: "Abținere",
  RESOLVE_REQUEST: "Soluționare cerere",
  ISSUE_DOCUMENT: "Emitere document",
  OTHER: "Alt tip",
};

export function statusLabel(value: string): string {
  return statusLabels[value] ?? value.replaceAll("_", " ");
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ro-RO", { dateStyle: "medium" }).format(
    new Date(value.length === 10 ? `${value}T00:00:00` : value),
  );
}

export function formatCurrency(value: string | number): string {
  return new Intl.NumberFormat("ro-RO", {
    style: "currency",
    currency: "RON",
    maximumFractionDigits: 2,
  }).format(Number(value));
}

export function dueInDays(value: string | null, reference = new Date()): number | null {
  if (!value) return null;
  const today = new Date(reference);
  today.setHours(0, 0, 0, 0);
  const dueDate = new Date(`${value}T00:00:00`);
  return Math.round((dueDate.getTime() - today.getTime()) / 86_400_000);
}

export function isOverdue(obligation: LegalObligation, reference = new Date()): boolean {
  const days = dueInDays(obligation.due_date, reference);
  return (
    days !== null &&
    days < 0 &&
    !["COMPLETED", "CANCELLED"].includes(obligation.status)
  );
}

export function dueDateHint(obligation: LegalObligation, reference = new Date()): string {
  if (obligation.status === "COMPLETED") return "Finalizată";
  if (obligation.status === "CANCELLED") return "Anulată";
  const days = dueInDays(obligation.due_date, reference);
  if (days === null) return "Fără termen";
  if (days < 0) return `Depășită cu ${Math.abs(days)} ${Math.abs(days) === 1 ? "zi" : "zile"}`;
  if (days === 0) return "Scadentă astăzi";
  if (days === 1) return "Scadentă mâine";
  return `Peste ${days} zile`;
}

export function downloadCsv(filename: string, rows: Array<Array<string | number>>): void {
  const csv = rows
    .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
    .join("\n");
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
