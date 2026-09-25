"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import {
  apiDownload,
  apiGet,
  apiUpload,
  type DocumentRecord,
} from "../../lib/api";
import {
  contractsGet,
  contractsPatch,
  contractsPost,
  type ContractDetail,
  type ContractRecord,
  type MilestoneStatus,
  type ObligationStatus,
  type PaymentStatus,
} from "../../lib/contracts";
import { formatDate } from "../../lib/legal";
import { Archive, BriefcaseBusiness, CalendarClock, CircleDollarSign, UsersRound } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../ui/data-state";
import { PageHeader } from "../ui/page-header";
import { StatusBadge } from "../ui/status-badge";
import { useSession } from "../legal/session-provider";

const money = new Intl.NumberFormat("ro-RO", { maximumFractionDigits: 2 });
const milestoneTransitions: Record<MilestoneStatus, MilestoneStatus[]> = {
  PENDING: ["IN_PROGRESS", "COMPLETED", "OVERDUE", "CANCELLED"],
  IN_PROGRESS: ["COMPLETED", "OVERDUE", "CANCELLED"],
  OVERDUE: ["IN_PROGRESS", "COMPLETED", "CANCELLED"],
  COMPLETED: [], CANCELLED: [],
};
const obligationTransitions: Record<ObligationStatus, ObligationStatus[]> = {
  OPEN: ["IN_PROGRESS", "COMPLETED", "OVERDUE", "CANCELLED"],
  IN_PROGRESS: ["COMPLETED", "OVERDUE", "CANCELLED"],
  OVERDUE: ["IN_PROGRESS", "COMPLETED", "CANCELLED"],
  COMPLETED: [], CANCELLED: [],
};
const paymentTransitions: Record<PaymentStatus, PaymentStatus[]> = {
  PLANNED: ["APPROVED", "CANCELLED"],
  APPROVED: ["PAID", "REJECTED", "CANCELLED"],
  PAID: [], REJECTED: [], CANCELLED: [],
};

export function ContractDetailView({ id }: { id: string }) {
  const { token, ready } = useSession();
  const [detail, setDetail] = useState<ContractDetail | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true); setError(null);
    try {
      const [contract, contractDocuments] = await Promise.all([
        contractsGet<ContractDetail>(`/contracts/${id}/overview`, token),
        apiGet<DocumentRecord[]>(`/documents?entity_type=Contract&entity_id=${id}`, token),
      ]);
      setDetail(contract); setDocuments(contractDocuments);
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Fișa nu a putut fi încărcată."); }
    finally { setLoading(false); }
  }, [id, token]);
  useEffect(() => { void load(); }, [load]);

  if (!ready || loading) return <LoadingState label="Încărcăm fișa contractuală…" />;
  if (error) return <ErrorState message={error} retry={() => void load()} />;
  if (!detail) return <EmptyState title="Fișa nu este disponibilă" description="Conectează aplicația sau revino la registru." icon={<Archive size={25} />} />;
  const item = detail.contract;
  return <>
    <PageHeader eyebrow="Fișă contractuală" title={item.contract_number} description={item.title} actions={<><EditContractForm contract={item} token={token} onChanged={load} /><Link className="button secondary" href="/contracts/registry">Înapoi la registru</Link></>} />
    <section className="detail-grid">
      <article className="detail-card"><h2>Date generale</h2><dl><div><dt>Status</dt><dd><StatusBadge status={item.status} /></dd></div><div><dt>Valoare</dt><dd>{money.format(Number(item.value))} {item.currency}</dd></div><div><dt>Perioadă</dt><dd>{formatDate(item.start_date)} – {formatDate(item.end_date)}</dd></div><div><dt>Semnat</dt><dd>{formatDate(item.signed_date)}</dd></div></dl></article>
      <article className="detail-card"><h2>Părți contractuale</h2><RelatedList empty="Nu există părți asociate." items={detail.parties.map((party) => ({ id: party.id, title: party.name, detail: `${party.role ?? party.party_type} · ${party.registration_number ?? "fără identificator"}` }))} icon={<UsersRound size={17} />} /><RelatedForm kind="parties" contractId={id} token={token} onCreated={load} /></article>
      <article className="detail-card span-two"><h2>Acte adiționale</h2><RelatedList empty="Nu există acte adiționale." items={detail.amendments.map((record) => ({ id: record.id, title: record.amendment_number, detail: `${formatDate(record.signed_date)} · ${record.description}` }))} icon={<BriefcaseBusiness size={17} />} /><RelatedForm kind="amendments" contractId={id} token={token} onCreated={load} /></article>
      <article className="detail-card"><h2>Jaloane și termene</h2><WorkflowList kind="milestones" contractId={id} token={token} onChanged={load} empty="Nu există jaloane." items={detail.milestones.map((record) => ({ id: record.id, title: record.title, detail: formatDate(record.due_date), status: record.status, transitions: milestoneTransitions[record.status] }))} icon={<CalendarClock size={17} />} /><RelatedForm kind="milestones" contractId={id} token={token} onCreated={load} /></article>
      <article className="detail-card"><h2>Obligații contractuale</h2><WorkflowList kind="obligations" contractId={id} token={token} onChanged={load} empty="Nu există obligații." items={detail.obligations.map((record) => ({ id: record.id, title: record.description, detail: formatDate(record.due_date), status: record.status, transitions: obligationTransitions[record.status] }))} icon={<Archive size={17} />} /><RelatedForm kind="obligations" contractId={id} token={token} onCreated={load} /></article>
      <article className="detail-card span-two"><h2>Plăți planificate</h2><WorkflowList kind="payments" contractId={id} token={token} onChanged={load} empty="Nu există plăți." items={detail.payments.map((record) => ({ id: record.id, title: `${money.format(Number(record.amount))} ${record.currency}`, detail: `${formatDate(record.due_date)} · ${record.reference ?? "fără referință"}`, status: record.status, transitions: paymentTransitions[record.status] }))} icon={<CircleDollarSign size={17} />} /><RelatedForm kind="payments" contractId={id} token={token} onCreated={load} /></article>
      <article className="detail-card span-two"><h2>Documente asociate</h2><DocumentSection contractId={id} documents={documents} token={token} onChanged={load} /></article>
    </section>
  </>;
}

function EditContractForm({ contract, token, onChanged }: { contract: ContractRecord; token: string; onChanged: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const entries = [...new FormData(event.currentTarget).entries()].filter(([, value]) => value !== "");
    setSaving(true); setError(null);
    try { await contractsPatch(`/contracts/${contract.id}`, token, Object.fromEntries(entries)); setOpen(false); await onChanged(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Contractul nu a putut fi actualizat."); }
    finally { setSaving(false); }
  };
  return <><button className="button primary" onClick={() => setOpen(true)} type="button">Editează contract</button>{open ? <div className="modal-backdrop" role="presentation"><section className="connection-modal contract-modal" role="dialog" aria-modal="true" aria-labelledby="contract-edit-title"><p className="eyebrow">GovContracts</p><h2 id="contract-edit-title">Editează contractul</h2><form className="case-form" onSubmit={submit}><label className="wide">Titlu<input defaultValue={contract.title} name="title" required /></label><label>Valoare<input defaultValue={contract.value} min="0.01" name="value" required step="0.01" type="number" /></label><label>Monedă<input defaultValue={contract.currency} maxLength={3} name="currency" required /></label><label>Data semnării<input defaultValue={contract.signed_date ?? ""} name="signed_date" type="date" /></label><label>Început<input defaultValue={contract.start_date} name="start_date" required type="date" /></label><label>Sfârșit<input defaultValue={contract.end_date} name="end_date" required type="date" /></label><label className="wide">Descriere<textarea defaultValue={contract.description ?? ""} name="description" rows={3} /></label>{error ? <div className="inline-error wide" role="alert">{error}</div> : null}<div className="modal-actions wide"><button className="button secondary" onClick={() => setOpen(false)} type="button">Renunță</button><button className="button primary" disabled={saving} type="submit">{saving ? "Se salvează…" : "Salvează modificările"}</button></div></form></section></div> : null}</>;
}

function DocumentSection({ contractId, documents, token, onChanged }: { contractId: string; documents: DocumentRecord[]; token: string; onChanged: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    data.set("entity_type", "Contract"); data.set("entity_id", contractId);
    data.set("category", "CONTRACT_DOCUMENT");
    setBusy(true); setError(null);
    try { await apiUpload("/documents", token, data); form.reset(); await onChanged(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Documentul nu a putut fi încărcat."); }
    finally { setBusy(false); }
  };
  const download = async (document: DocumentRecord) => {
    setBusy(true); setError(null);
    try {
      const blob = await apiDownload(`/documents/${document.id}/download`, token);
      const url = URL.createObjectURL(blob); const link = window.document.createElement("a");
      link.href = url; link.download = document.original_filename; link.click(); URL.revokeObjectURL(url);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Documentul nu a putut fi descărcat."); }
    finally { setBusy(false); }
  };
  return <><RelatedList empty="Nu există documente asociate." items={documents.map((record) => ({ id: record.id, title: record.original_filename, detail: `${record.category.replaceAll("_", " ")} · ${Math.ceil(record.size_bytes / 1024)} KB` }))} icon={<Archive size={17} />} />{documents.length ? <div className="document-actions">{documents.map((document) => <button className="inline-action" disabled={busy} key={document.id} onClick={() => void download(document)} type="button">Descarcă {document.original_filename}</button>)}</div> : null}<form className="document-upload" onSubmit={upload}><label>Adaugă document<input name="file" required type="file" /></label><button className="button secondary" disabled={busy} type="submit">{busy ? "Se procesează…" : "Încarcă"}</button></form>{error ? <div className="inline-error" role="alert">{error}</div> : null}</>;
}

function RelatedList({ items, empty, icon }: { items: Array<{ id: string; title: string; detail: string }>; empty: string; icon: ReactNode }) {
  if (!items.length) return <p className="muted">{empty}</p>;
  return <ul className="detail-list">{items.map((item) => <li key={item.id}><span className="item-icon">{icon}</span><div><strong>{item.title}</strong><p>{item.detail}</p></div></li>)}</ul>;
}

function WorkflowList({ items, empty, icon, kind, contractId, token, onChanged }: {
  items: Array<{ id: string; title: string; detail: string; status: string; transitions: string[] }>;
  empty: string; icon: ReactNode; kind: "milestones" | "obligations" | "payments";
  contractId: string; token: string; onChanged: () => Promise<void>;
}) {
  const [updating, setUpdating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const update = async (itemId: string, status: string) => {
    setUpdating(itemId); setError(null);
    try {
      await contractsPatch(`/contracts/${contractId}/${kind}/${itemId}/status`, token, { status });
      await onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Statusul nu a putut fi actualizat.");
    } finally { setUpdating(null); }
  };
  if (!items.length) return <p className="muted">{empty}</p>;
  return <><ul className="detail-list">{items.map((item) => <li key={item.id}><span className="item-icon">{icon}</span><div><strong>{item.title}</strong><p>{item.detail}</p><StatusBadge status={item.status} />{item.transitions.length ? <select aria-label={`Actualizează statusul pentru ${item.title}`} className="inline-status-select" defaultValue="" disabled={updating === item.id} onChange={(event) => { if (event.target.value) void update(item.id, event.target.value); }}><option value="">Actualizează…</option>{item.transitions.map((status) => <option key={status}>{status}</option>)}</select> : null}</div></li>)}</ul>{error ? <div className="inline-error" role="alert">{error}</div> : null}</>;
}

type RelatedKind = "parties" | "amendments" | "milestones" | "obligations" | "payments";

function RelatedForm({ kind, contractId, token, onCreated }: { kind: RelatedKind; contractId: string; token: string; onCreated: () => Promise<void> }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const entries = [...new FormData(event.currentTarget).entries()].filter(([, value]) => value !== "");
    setSaving(true); setError(null);
    try {
      await contractsPost(`/contracts/${contractId}/${kind}`, token, Object.fromEntries(entries));
      event.currentTarget.reset(); await onCreated();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Înregistrarea nu a putut fi salvată."); }
    finally { setSaving(false); }
  };
  return <details className="related-create"><summary>Adaugă înregistrare</summary><form className="case-form" onSubmit={submit}>{kind === "parties" ? <><label className="wide">Denumire<input name="name" required /></label><label>Tip<input defaultValue="SUPPLIER" name="party_type" required /></label><label>Rol<input defaultValue="CONTRACTOR" name="role" required /></label><label>Cod fiscal<input name="registration_number" /></label><label className="wide">E-mail<input name="email" type="email" /></label></> : null}{kind === "amendments" ? <><label>Număr<input name="amendment_number" required /></label><label>Data semnării<input name="signed_date" required type="date" /></label><label>Modificare valoare<input name="value_change" step="0.01" type="number" /></label><label>Termen nou<input name="end_date_change" type="date" /></label><label className="wide">Descriere<textarea name="description" required /></label></> : null}{kind === "milestones" ? <><label className="wide">Denumire<input name="title" required /></label><label>Termen<input name="due_date" required type="date" /></label></> : null}{kind === "obligations" ? <><label className="wide">Descriere<textarea name="description" required /></label><label>Termen<input name="due_date" type="date" /></label></> : null}{kind === "payments" ? <><label>Valoare<input min="0.01" name="amount" required step="0.01" type="number" /></label><label>Monedă<input defaultValue="RON" name="currency" required /></label><label>Scadență<input name="due_date" required type="date" /></label><label className="wide">Referință<input name="reference" /></label></> : null}{error ? <div className="inline-error wide" role="alert">{error}</div> : null}<button className="button primary" disabled={saving} type="submit">{saving ? "Se salvează…" : "Salvează"}</button></form></details>;
}
