"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CV_SECTIONS, ORIGINAL_CV_URL, cvProfileApi, entryLabel, type CvSection, type CvSections, type CvSnapshot } from "../lib/cv-profile-api";
import CvFields from "./CvFields";

const DRAFT_KEY = "radar.cv.history-draft";

export default function CvHistoryEditor({ onChanged }: { onChanged?: () => void }) {
  const [saved, setSaved] = useState<CvSnapshot | null>(null);
  const [dirty, setDirty] = useState<Partial<CvSections>>({});
  const [undo, setUndo] = useState<Partial<CvSections> | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const ready = useRef(false);
  const load = useCallback(async () => {
    try {
      const next = await cvProfileApi.read(); setSaved(next);
      if (!ready.current) {
        try {
          const cached = JSON.parse(localStorage.getItem(DRAFT_KEY) ?? "null");
          if (cached?.sections && cached?.base) {
            const compatible = Object.keys(cached.sections).every((key) => JSON.stringify(cached.base[key]) === JSON.stringify(next.sections[key as CvSection]));
            if (compatible) { setDirty(cached.sections); setNote("Recuperamos tus cambios sin guardar."); }
            else setNote("Tu CV cambió desde el último borrador. Revisa los datos actuales antes de editar.");
          }
        } catch { /* Browser storage is optional. */ }
        ready.current = true;
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo cargar tu CV."); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const reload = async () => {
    try {
      const next = await cvProfileApi.read();
      const conflict = saved && (Object.keys(dirty) as CvSection[]).some((key) => JSON.stringify(saved.sections[key]) !== JSON.stringify(next.sections[key]));
      if (conflict) { setError("Esta sección cambió en otra vista. Tu borrador sigue aquí: copia lo que necesites y descártalo para cargar los datos actuales."); return; }
      setSaved(next); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo recargar."); }
  };

  const change = (section: CvSection, entries: CvSections[CvSection]) => {
    const next = { ...dirty, [section]: entries }; setDirty(next); setUndo(null); setNote("Borrador guardado en este navegador. Pulsa Guardar cambios para actualizar tu perfil.");
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ sections: next, base: saved?.sections })); } catch { setNote("Cambios pendientes. Pulsa Guardar cambios antes de salir."); }
  };
  const save = async (sections: Partial<CvSections>, isUndo = false) => {
    if (!saved) return;
    setBusy(true); setError("");
    try {
      const result = await cvProfileApi.save(sections, saved.revision);
      setSaved({ ...result, original_name: saved.original_name }); setDirty({}); setUndo(isUndo ? null : result.undo);
      setNote([isUndo ? "Cambio deshecho." : "Tu trayectoria está guardada.", ...result.warnings].join(" "));
      try { localStorage.removeItem(DRAFT_KEY); } catch { /* Optional. */ }
      onChanged?.();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo guardar."); }
    finally { setBusy(false); }
  };
  return <section className="mycv-history" aria-label="Tu trayectoria">
    <h2>Tu trayectoria</h2><p className="m-sub">Mantén aquí tu experiencia, estudios y proyectos. Se reutilizan al comparar ofertas y preparar tu CV.</p>
    {saved?.original_name && <p><a className="mycv-link" href={ORIGINAL_CV_URL} download>Descargar mi archivo original · {saved.original_name}</a><small className="mycv-summary">Los cambios en tu perfil no modifican este archivo.</small></p>}
    {error && <div role="alert" className="mycv-message">{error} <button type="button" className="mycv-link" disabled={busy} onClick={() => void reload()}>Recargar datos</button></div>}
    {note && <p role="status" className="mycv-message">{note}</p>}
    {!saved ? <p>Cargando tu trayectoria…</p> : (Object.keys(CV_SECTIONS) as CvSection[]).map((section) => {
      const entries = dirty[section] ?? saved.sections[section];
      return <details key={section} className="mycv-section"><summary>{CV_SECTIONS[section].label} · {entries.length}{dirty[section] ? " · cambios pendientes" : ""}</summary>
        {entries.length > 0 && <p className="mycv-summary">{entries.map(entryLabel).join(" / ")}</p>}
        <CvFields section={section} entries={entries} disabled={busy} onChange={(next) => change(section, next)} />
      </details>;
    })}
    {Object.keys(dirty).length > 0 && <div className="mycv-actions"><button type="button" className="mycv-button primary" disabled={busy} onClick={() => void save(dirty)}>{busy ? "Guardando…" : "Guardar cambios"}</button><button type="button" className="mycv-link" disabled={busy} onClick={() => { setDirty({}); setNote(""); setError(""); void load(); try { localStorage.removeItem(DRAFT_KEY); } catch { /* Optional. */ } }}>Descartar borrador</button></div>}
    {undo && <button type="button" className="mycv-link" disabled={busy} onClick={() => void save(undo, true)}>Deshacer último cambio</button>}
  </section>;
}
