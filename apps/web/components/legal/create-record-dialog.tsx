"use client";

import { useEffect, useState, type FormEvent } from "react";
import { apiGet, apiPost, type CourtDecision, type LegalCase, type LegalObligation } from "../../lib/api";
import { documentsUpload } from "../../lib/documents";
import { X } from "../ui/icons";
import type { OperationalView } from "./operational-page";

const creatableViews: OperationalView[] = ["cases", "decisions", "obligations", "enforcements", "penalties", "documents"];
export function canCreate(view: OperationalView): boolean { return creatableViews.includes(view); }

export function CreateRecordDialog({ view, token, onCreated }: { view: OperationalView; token: string; onCreated: () => Promise<void> }) {
  const [open, setOpen] = useState(false); const [saving, setSaving] = useState(false); const [error, setError] = useState<string | null>(null);
  const [cases, setCases] = useState<LegalCase[]>([]); const [decisions, setDecisions] = useState<CourtDecision[]>([]); const [obligations, setObligations] = useState<LegalObligation[]>([]);
  useEffect(() => {
    if (!open || !token) return;
    const requests: Array<Promise<void>> = [];
    if (view === "decisions") requests.push(apiGet<LegalCase[]>("/legal/cases", token).then(setCases));
    if (view === "obligations") requests.push(apiGet<CourtDecision[]>("/legal/decisions", token).then(setDecisions));
    if (["enforcements", "penalties"].includes(view)) requests.push(apiGet<LegalObligation[]>("/legal/obligations", token).then(setObligations));
    void Promise.all(requests).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Listele auxiliare nu au putut fi încărcate."));
  }, [open, token, view]);
  if (!canCreate(view)) return null;
  const labels: Partial<Record<OperationalView, string>> = { cases: "Dosar nou", decisions: "Hotărâre nouă", obligations: "Obligație nouă", enforcements: "Executare nouă", penalties: "Regulă nouă", documents: "Încarcă document" };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setSaving(true); setError(null); const form = event.currentTarget; const data = new FormData(form); const value = (name: string) => String(data.get(name) ?? ""); const optional = (name: string) => value(name) || null;
    try {
      if (view === "cases") await apiPost("/legal/cases", token, { case_number: value("case_number"), court: value("court"), subject: value("subject"), filing_date: optional("filing_date"), external_reference: optional("external_reference") });
      if (view === "decisions") await apiPost(`/legal/cases/${value("case_id")}/decisions`, token, { decision_number: value("decision_number"), decision_date: value("decision_date"), final_date: optional("final_date"), decision_type: value("decision_type"), summary: optional("summary") });
      if (view === "obligations") await apiPost("/legal/obligations", token, { court_decision_id: value("court_decision_id"), obligation_type: value("obligation_type"), description: value("description"), due_date: optional("due_date") });
      if (view === "enforcements") await apiPost("/legal/enforcements", token, { obligation_id: value("obligation_id"), file_number: value("file_number"), enforcement_officer: optional("enforcement_officer"), start_date: value("start_date") });
      if (view === "penalties") { const calculation = value("calculation_type"); await apiPost("/legal/penalties/rules", token, { obligation_id: value("obligation_id"), calculation_type: calculation, daily_amount: calculation === "DAILY_AMOUNT" ? optional("daily_amount") : null, percentage: calculation === "PERCENTAGE_OF_BASE" ? optional("percentage") : null, base_value: calculation === "PERCENTAGE_OF_BASE" ? optional("base_value") : null, start_date: value("start_date"), end_date: optional("end_date") }); }
      if (view === "documents") { const file = data.get("file"); if (!(file instanceof File) || !file.size) throw new Error("Selectează un fișier."); await documentsUpload(token, data); }
      form.reset(); setOpen(false); await onCreated();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Înregistrarea nu a putut fi salvată."); }
    finally { setSaving(false); }
  };
  return <><button className="button primary" onClick={() => setOpen(true)} type="button">{labels[view]}</button>{open ? <div className="modal-backdrop"><section className="record-modal" role="dialog" aria-modal="true" aria-labelledby="record-title"><button className="modal-close icon-button" onClick={() => setOpen(false)} aria-label="Închide"><X size={18} /></button><p className="eyebrow">Înregistrare GovLegal</p><h2 id="record-title">{labels[view]}</h2><form className="record-form" onSubmit={submit}>{fields(view, cases, decisions, obligations)}{error ? <div className="inline-error" role="alert">{error}</div> : null}<div className="record-actions"><button className="button secondary" onClick={() => setOpen(false)} type="button">Renunță</button><button className="button primary" disabled={saving} type="submit">{saving ? "Se salvează…" : "Salvează"}</button></div></form></section></div> : null}</>;
}

function fields(view: OperationalView, cases: LegalCase[], decisions: CourtDecision[], obligations: LegalObligation[]) {
  if (view === "cases") return <><label>Număr dosar<input name="case_number" required /></label><label>Instanță<input name="court" required /></label><label>Data înregistrării<input name="filing_date" type="date" /></label><label>Referință externă<input name="external_reference" /></label><label className="full">Obiect<textarea name="subject" required rows={3} /></label></>;
  if (view === "decisions") return <><label className="full">Dosar<select name="case_id" required><option value="">Selectează dosarul</option>{cases.map((item) => <option key={item.id} value={item.id}>{item.case_number} · {item.court}</option>)}</select></label><label>Număr hotărâre<input name="decision_number" required /></label><label>Tip<input name="decision_type" required /></label><label>Data hotărârii<input name="decision_date" required type="date" /></label><label>Data definitivă<input name="final_date" type="date" /></label><label className="full">Rezumat<textarea name="summary" rows={3} /></label></>;
  if (view === "obligations") return <><label className="full">Hotărâre<select name="court_decision_id" required><option value="">Selectează hotărârea</option>{decisions.map((item) => <option key={item.id} value={item.id}>{item.decision_number} · {item.decision_type}</option>)}</select></label><label>Tip<select name="obligation_type"><option value="DO">Executare</option><option value="PAY">Plată</option><option value="REFRAIN">Abținere</option><option value="RESOLVE_REQUEST">Soluționare cerere</option><option value="ISSUE_DOCUMENT">Emitere document</option><option value="OTHER">Alt tip</option></select></label><label>Termen<input name="due_date" type="date" /></label><label className="full">Descriere<textarea name="description" required rows={3} /></label></>;
  if (view === "enforcements") return <><label className="full">Obligație<select name="obligation_id" required><option value="">Selectează obligația</option>{obligations.map((item) => <option key={item.id} value={item.id}>{item.description.slice(0, 90)}</option>)}</select></label><label>Număr dosar executare<input name="file_number" required /></label><label>Data deschiderii<input name="start_date" required type="date" /></label><label className="full">Executor / responsabil<input name="enforcement_officer" /></label></>;
  if (view === "penalties") return <><label className="full">Obligație<select name="obligation_id" required><option value="">Selectează obligația</option>{obligations.map((item) => <option key={item.id} value={item.id}>{item.description.slice(0, 90)}</option>)}</select></label><label>Metodă<select name="calculation_type"><option value="DAILY_AMOUNT">Sumă zilnică</option><option value="PERCENTAGE_OF_BASE">Procent din bază / zi</option></select></label><label>Început<input name="start_date" required type="date" /></label><label>Sumă zilnică<input min="0" name="daily_amount" step="0.01" type="number" /></label><label>Procent<input min="0" name="percentage" step="0.0001" type="number" /></label><label>Valoare bază<input min="0" name="base_value" step="0.01" type="number" /></label><label>Sfârșit<input name="end_date" type="date" /></label></>;
  return <><label>Tip resursă<select name="entity_type" required><option value="LegalCase">Dosar juridic</option><option value="LegalObligation">Obligație juridică</option><option value="CourtDecision">Hotărâre</option><option value="EnforcementProceeding">Executare</option></select></label><label>ID resursă<input name="entity_id" required /></label><label>Categorie<input name="category" required value="SUPPORTING_DOCUMENT" /></label><label>Clasificare<select name="classification"><option value="INTERNAL">Intern</option><option value="PUBLIC">Public</option><option value="CONFIDENTIAL">Confidențial</option></select></label><label>Retenție până la<input name="retention_until" type="date" /></label><label>Fișier<input accept=".pdf,.txt,.csv,.docx,.xlsx,.png,.jpg,.jpeg" name="file" required type="file" /></label></>;
}
