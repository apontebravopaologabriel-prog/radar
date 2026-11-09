"use client";
import { useState, type FormEvent } from "react";
import { saveProcess, STAGES, type ProcessInput, type ProcessItem } from "../lib/processes-api";

export default function ProcessForm({ initial, id, onSaved, onCancel }: { initial?: ProcessInput; id?: string; onSaved: (item: ProcessItem) => void; onCancel: () => void }) {
  const [value, setValue] = useState<ProcessInput>(initial ?? { company: "", title: "", stage: "contact" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError("");
    try {
      const saved = await saveProcess({ ...value, url: value.url || null, due_date: value.due_date || null, next_step: value.next_step || null, notes: value.notes || null }, id);
      window.dispatchEvent(new CustomEvent("radar:jobs-changed")); onSaved(saved);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo guardar el proceso"); }
    finally { setBusy(false); }
  }
  return <form className="process-form" onSubmit={(event) => void submit(event)}>
    <fieldset disabled={busy}><legend>{id ? "Editar proceso" : "Registrar contacto"}</legend>
      <label>Empresa<input required maxLength={300} value={value.company} onChange={(e) => setValue({ ...value, company: e.target.value })} /></label>
      <label>Puesto<input required maxLength={500} value={value.title} onChange={(e) => setValue({ ...value, title: e.target.value })} /></label>
      <label>Etapa<select value={value.stage ?? "contact"} onChange={(e) => setValue({ ...value, stage: e.target.value as ProcessInput["stage"] })}>{Object.entries(STAGES).map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>
      <details open={Boolean(id)}><summary>Próximo paso, fecha y otros detalles (opcional)</summary>
      <label>Próximo paso (opcional)<input maxLength={500} placeholder="Ej. Preparar la prueba técnica" value={value.next_step ?? ""} onChange={(e) => setValue({ ...value, next_step: e.target.value })} /></label>
      <label>Fecha (opcional)<input type="date" value={value.due_date ?? ""} onInput={(e) => setValue({ ...value, due_date: e.currentTarget.value })} /></label>
      <label>Enlace (opcional)<input type="url" maxLength={2000} value={value.url ?? ""} onChange={(e) => setValue({ ...value, url: e.target.value })} /></label>
      <label>Nota (opcional)<textarea maxLength={5000} value={value.notes ?? ""} onChange={(e) => setValue({ ...value, notes: e.target.value })} /></label>
      </details>
      {error && <p role="alert">{error}</p>}
      <div className="process-actions"><button type="submit">{busy ? "Guardando…" : "Guardar proceso"}</button><button type="button" onClick={onCancel}>Cancelar</button></div>
    </fieldset>
  </form>;
}
