"use client";

import { useEffect, useRef, useState } from "react";
import { CV_SECTIONS, type CvSection } from "../lib/cv-profile-api";
import { setupApi, type SetupDraft } from "../lib/setup-api";
import CvFields from "./CvFields";
import "./my-cv.css";

const DIFF_LABELS: Record<string, string> = { name: "Nombre", contact: "Contacto", headline: "Titular", summary: "Resumen", detected_skills: "Herramientas mencionadas", ...Object.fromEntries(Object.entries(CV_SECTIONS).map(([key, value]) => [key, value.label])) };
const empty = (career: string, name: string): SetupDraft => ({ career_id: career, name, contact: {}, education: [], experience: [], source_name: "", source_text: "", detected_skills: [] });
function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Sin datos";
  if (Array.isArray(value)) return value.length ? value.map((item) => typeof item === "string" ? item : Object.values(item).filter(Boolean).map((v) => Array.isArray(v) ? v.join("; ") : String(v)).join(" · ")).join("\n") : "Sin registros";
  if (typeof value === "object") return Object.values(value).filter(Boolean).join(" · ");
  return String(value);
}

export default function CvImportPanel({ careerId, initialName = "", onSaved, allowManual = false }: { careerId: string; initialName?: string; onSaved: () => void; allowManual?: boolean }) {
  const [draft, setDraft] = useState<SetupDraft | null>(null);
  const [review, setReview] = useState<Awaited<ReturnType<typeof setupApi.changes>> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [dragging, setDragging] = useState(false);
  const [undo, setUndo] = useState<{ backup: string; revision: string } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const generation = useRef(0);
  const saving = useRef(Promise.resolve());
  const latestDraft = useRef<SetupDraft | null>(null);
  const confirmed = useRef(false);
  latestDraft.current = draft;
  useEffect(() => () => {
    const pending = latestDraft.current;
    if (pending && !confirmed.current) {
      void saving.current.catch(() => undefined).then(() => setupApi.save(pending)).catch(() => undefined);
    }
  }, []);
  useEffect(() => {
    let active = true;
    setupApi.state().then((state) => { if (active && state.draft) setDraft({ ...state.draft, career_id: careerId }); }).catch(() => undefined);
    return () => { active = false; };
  }, [careerId]);
  useEffect(() => {
    if (!draft || busy) return;
    const timer = window.setTimeout(() => {
      saving.current = saving.current.catch(() => undefined).then(async () => {
        try { await setupApi.save(draft); setNote("Borrador guardado en este equipo."); }
        catch { setNote("No se pudo guardar el borrador. Conserva esta pantalla abierta e inténtalo de nuevo."); }
      });
    }, 650);
    return () => window.clearTimeout(timer);
  }, [draft, busy]);

  const change = (next: SetupDraft) => { setDraft(next); setReview(null); setNote(""); };
  const upload = async (file?: File) => {
    if (!file || busy) return;
    if (file.size > 8 * 1024 * 1024) { setError("Adjunta un CV de hasta 8 MB."); return; }
    const current = ++generation.current;
    confirmed.current = false;
    setBusy(true); setError(""); setNote(""); setReview(null);
    try {
      await saving.current;
      const next = await setupApi.preview(file, careerId);
      if (generation.current === current) setDraft({ ...next, name: next.name || initialName });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo leer el CV."); }
    finally { setBusy(false); }
  };
  const inspect = async () => {
    if (!draft) return;
    setBusy(true); setError("");
    try { await saving.current; const next = await setupApi.changes(draft); setReview(next); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudieron revisar los cambios."); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    if (!draft || !review) return;
    setBusy(true); setError("");
    try {
      await saving.current;
      const result = await setupApi.confirm({ ...draft, base_revision: review.revision });
      confirmed.current = true;
      setDraft(null); setReview(null); setUndo(result.undo); setNote(["CV guardado.", ...result.warnings].join(" ")); onSaved();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo guardar el CV."); setReview(null); }
    finally { setBusy(false); }
  };
  return <section className="mycv-import" aria-label="Importar tu CV">
    <div className={`mycv-drop ${dragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void upload(event.dataTransfer.files[0]); }}>
      <h3>{draft ? "Revisa tu CV" : "Arrastra tu CV aquí"}</h3>
      <p>PDF con texto o Word .docx · hasta 8 MB. Se lee en este equipo, sin clave de IA.</p>
      <button type="button" className="mycv-button" disabled={busy} onClick={() => fileInput.current?.click()}>{busy ? "Procesando…" : draft ? "Elegir otro archivo" : "Elegir archivo"}</button>
      {allowManual && !draft && <button type="button" className="mycv-link" onClick={() => { confirmed.current = false; setDraft(empty(careerId, initialName)); }}>Completar mis datos a mano</button>}
      <input ref={fileInput} type="file" accept=".pdf,.docx" hidden disabled={busy} onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ""; }} />
    </div>
    {error && <p className="mycv-message" role="alert">{error}</p>}
    {note && <p className="mycv-message" role="status">{note}</p>}
    {undo && !draft && <button type="button" className="mycv-link" disabled={busy} onClick={async () => {
      setBusy(true); setError("");
      try { const result = await setupApi.undoImport(undo); setUndo(null); setNote(["Importación deshecha.", ...result.warnings].join(" ")); onSaved(); }
      catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo deshacer."); }
      finally { setBusy(false); }
    }}>Deshacer importación</button>}
    {draft && <div className="mycv-review">
      <p>{draft.source_name || "Perfil sin archivo"}. Revisa lo extraído. Tus datos actuales se conservan hasta confirmar.</p>
      {(draft.warnings ?? []).map((warning) => <p className="mycv-message" key={warning}>{warning}</p>)}
      <fieldset disabled={busy}><legend>Datos personales</legend><div className="mycv-grid">
        <label>Nombre *<input maxLength={80} value={draft.name} onChange={(event) => change({ ...draft, name: event.target.value })} /></label>
        {(["email", "phone", "linkedin"] as const).map((key) => <label key={key}>{key === "email" ? "Correo" : key === "phone" ? "Teléfono" : "LinkedIn"}<input maxLength={120} value={draft.contact[key] ?? ""} onChange={(event) => change({ ...draft, contact: { ...draft.contact, [key]: event.target.value } })} /></label>)}
        <label className="mycv-wide">Titular<input maxLength={200} value={draft.headline ?? ""} onChange={(event) => change({ ...draft, headline: event.target.value })} /></label>
        <label className="mycv-wide">Resumen<textarea rows={3} maxLength={600} value={draft.summary ?? ""} onChange={(event) => change({ ...draft, summary: event.target.value })} /></label>
      </div></fieldset>
      {(Object.keys(CV_SECTIONS) as CvSection[]).map((section) => <details key={section} className="mycv-section">
        <summary>{CV_SECTIONS[section].label} · {(draft[section] ?? []).length} registros</summary>
        <CvFields section={section} entries={draft[section] ?? []} disabled={busy} onChange={(entries) => change({ ...draft, [section]: entries })} />
      </details>)}
      {draft.detected_skills.length > 0 && <p>Herramientas mencionadas: {draft.detected_skills.join(" · ")}. Sin nivel asignado.</p>}
      {draft.source_text && <details className="mycv-section"><summary>Consultar el texto del archivo</summary><pre>{draft.source_text}</pre></details>}
      {review && <section className="mycv-changes" aria-label="Cambios que se guardarán"><h3>Esto cambiará en tu perfil</h3>
        <p>Se añaden o actualizan estos datos. Los registros que no aparecen en el archivo se conservan.</p>
        {Object.entries(review.diff).length === 0 ? <p>El contenido ya está en tu perfil. Puedes confirmar para conservar este archivo como tu CV original.</p> : Object.entries(review.diff).map(([key, value]) => <details key={key}><summary>{DIFF_LABELS[key] ?? key}</summary><div className="mycv-grid"><div><b>Ahora</b><pre>{show(value.before)}</pre></div><div><b>Después</b><pre>{show(value.after)}</pre></div></div></details>)}
      </section>}
      <div className="mycv-actions">{review
        ? <><button type="button" className="mycv-button primary" disabled={busy || !draft.name.trim()} onClick={() => void confirm()}>Confirmar y guardar</button><button type="button" className="mycv-link" disabled={busy} onClick={() => setReview(null)}>Volver a revisar</button></>
        : <button type="button" className="mycv-button primary" disabled={busy || !draft.name.trim()} onClick={() => void inspect()}>Revisar cambios</button>}
      </div>
    </div>}
  </section>;
}
