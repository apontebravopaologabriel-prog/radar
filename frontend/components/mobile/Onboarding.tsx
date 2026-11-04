"use client";

import { useEffect, useState } from "react";
import { api, type Career } from "../../lib/mobile-api";
import { setupApi, type SetupDraft, type CvEntry } from "../../lib/setup-api";
import RefreshPanel from "./RefreshPanel";

export default function Onboarding({ onDone, onError, onPause }: { onDone: () => void; onError: (e: unknown) => void; onPause?: () => void }) {
  const [career, setCareer] = useState<Career | null>(null);
  const [draft, setDraft] = useState<SetupDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [note, setNote] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([api.career(), setupApi.state(), api.me()]).then(([c, state, me]) => {
      if (!active) return;
      setCareer(c);
      setDraft(state.draft ?? {career_id: c.active, name: me.name, contact: me.contact, education: [], experience: [], detected_skills: [], source_name: "", source_text: ""});
    }).catch(onError);
    return () => { active = false; };
  }, [onError]);
  if (!career || !draft) return <p className="m-empty">Cargando…</p>;
  const change = (key: keyof SetupDraft, value: SetupDraft[typeof key]) => setDraft({...draft, [key]: value});
  const entry = (section: "education" | "experience", index: number, key: string, value: string) => {
    const values = draft[section].map((item, i) => i === index ? {...item, [key]: value} : item);
    change(section, values);
  };
  const upload = async (file?: File) => {
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) { onError(new Error("El CV admite hasta 8 MB.")); return; }
    setBusy(true);
    try {
      const parsed = await setupApi.preview(file, draft.career_id);
      setDraft({...parsed, name: parsed.name || draft.name});
      await setupApi.save({...parsed, name: parsed.name || draft.name});
      setNote("CV leído. Revisa y corrige los datos antes de confirmar.");
    } catch (error) { onError(error); } finally { setBusy(false); }
  };
  const save = async () => {
    setBusy(true);
    try {
      const result = await setupApi.confirm(draft);
      try { localStorage.setItem("radar.market", draft.career_id); } catch { /* Storage is optional. */ }
      setNote(result.warnings.join(" "));
      setSaved(true);
    } catch (error) { onError(error); } finally { setBusy(false); }
  };
  const pause = async () => {
    setBusy(true);
    try { await setupApi.save(draft); onPause?.(); setNote("Borrador guardado en este equipo."); }
    catch (error) { onError(error); } finally { setBusy(false); }
  };
  if (saved) return <div className="m-stack">
    <header className="m-head"><span className="m-eyebrow">[LISTO]</span><h1>Tu perfil está guardado</h1><p>Traeremos ofertas del mercado elegido para Lima/Callao. Todas las áreas, últimos 7 días.</p></header>
    {note && <p role="status">{note}</p>}
    <RefreshPanel places={["Lima"]} autoStart onError={onError} />
    <button className="m-primary" onClick={onDone}>Ir al mapa</button>
  </div>;
  const sections: ["education" | "experience", string, string[]][] = [["education", "Estudios", ["program", "institution", "status"]], ["experience", "Experiencia", ["role", "company", "from", "to"]]];
  const labels: Record<string, string> = {program: "Carrera / programa", institution: "Institución", status: "Estado o grado", role: "Cargo", company: "Empresa", from: "Inicio (AAAA-MM)", to: "Fin (AAAA-MM o actual)"};
  return <div className="m-stack">
    <header className="m-head"><span className="m-eyebrow">[INICIO]</span><h1>Empieza con tu CV</h1><p>Elige un mercado y revisa tu perfil. Puedes continuar sin archivo.</p></header>
    <section className="m-card"><h2>Mercado · Lima/Callao</h2>
      <label>Carrera<select disabled={busy} value={draft.career_id} onChange={(e) => change("career_id", e.target.value)}>{career.tracks.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
      <label>Adjuntar CV (PDF o DOCX)<input type="file" accept=".pdf,.docx" disabled={busy} onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = ""; }} /></label>
      <p className="m-sub">Se procesa en este equipo. Hasta 8 MB; PDF con texto o Word .docx. No necesitas clave de IA.</p>
    </section>
    {note && <p role="status">{note}</p>}
    <section className="m-card"><h2>Revisa tus datos</h2>
      <label>Nombre<input disabled={busy} value={draft.name} onChange={(e) => change("name", e.target.value)} /></label>
      {(["email", "phone"] as const).map((key) => <label key={key}>{key === "email" ? "Correo" : "Teléfono"}<input disabled={busy} value={draft.contact[key] ?? ""} onChange={(e) => change("contact", {...draft.contact, [key]: e.target.value})} /></label>)}
    </section>
    {sections.map(([section, title, fields]) => <section className="m-card" key={section}><h2>{title}</h2>
      {draft[section].map((item: CvEntry, i) => <fieldset key={i} disabled={busy}><legend>{title} {i + 1}</legend>
        {fields.map((key) => <label key={key}>{labels[key]}<input value={String(item[key] ?? "")} onChange={(e) => entry(section, i, key, e.target.value)} /></label>)}
        <button type="button" onClick={() => change(section, draft[section].filter((_, n) => n !== i))}>Quitar registro</button>
      </fieldset>)}
      <button type="button" disabled={busy} onClick={() => change(section, [...draft[section], Object.fromEntries(fields.map((key) => [key, ""]))])}>+ Añadir</button>
    </section>)}
    {draft.detected_skills.length > 0 && <section className="m-card"><h2>Herramientas mencionadas</h2><p>{draft.detected_skills.join(" · ")}</p><p className="m-sub">Sin nivel asignado. Puedes declarar tus niveles en Ajustes después.</p></section>}
    {draft.source_text && <details className="m-card"><summary>Texto extraído · verificar experiencia y estudios</summary><pre style={{whiteSpace: "pre-wrap", maxHeight: 280, overflow: "auto"}}>{draft.source_text}</pre></details>}
    <p className="m-sub">El formato puede alterar la lectura. Confirma solo datos ciertos; los registros existentes se conservan al importar.</p>
    <button className="m-primary" disabled={busy || !draft.name.trim()} onClick={save}>{busy ? "Procesando…" : "Confirmar perfil y buscar ofertas"}</button>
    <button type="button" disabled={busy} onClick={pause}>Guardar borrador y continuar después</button>
  </div>;
}
