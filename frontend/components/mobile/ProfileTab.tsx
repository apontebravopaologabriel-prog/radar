"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CV_PHOTO_URL } from "../../lib/cv-api";
import { api, type Career, type MeProfile } from "../../lib/mobile-api";

const LEVELS = [["basic", "Básico"], ["intermediate", "Medio"], ["advanced", "Alto"]] as const;
const LEVEL_LABEL: Record<string, string> = { basic: "Básico", intermediate: "Medio", advanced: "Alto", none: "—" };
const MODES = [["onsite", "Presencial"], ["hybrid", "Híbrido"], ["remote", "Remoto"]] as const;
const CONTACT = [["email", "Correo"], ["phone", "Teléfono"], ["linkedin", "LinkedIn"]] as const;
const UNDO_MS = 9000;

type Toast = { text: string; undo?: Record<string, unknown>; warnings: string[] };

/** Campo de una línea o de varias que guarda al salir (Enter en una línea). Si el servidor lo rechaza, se remonta con el valor real. */
function Field({ label, value, onCommit, multiline, list, placeholder, maxLength }: {
  label: string; value: string; onCommit: (value: string) => void; multiline?: boolean; list?: string; placeholder?: string; maxLength?: number;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const commit = () => { const next = draft.trim(); if (next !== value) onCommit(next); };
  return (
    <label className="set-field">
      <span>{label}</span>
      {multiline
        ? <textarea rows={3} value={draft} maxLength={maxLength} placeholder={placeholder} onChange={(e) => setDraft(e.target.value)} onBlur={commit} />
        : <input value={draft} list={list} maxLength={maxLength} placeholder={placeholder} onChange={(e) => setDraft(e.target.value)} onBlur={commit}
            onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") { setDraft(value); e.currentTarget.blur(); } }} />}
    </label>
  );
}

/** Lista de etiquetas con quitar (✕) y un campo para añadir; las sugerencias salen de un datalist. */
function Chips({ label, items, suggestions, onAdd, onRemove, placeholder }: {
  label: string; items: string[]; suggestions?: string[]; onAdd: (value: string) => void; onRemove: (value: string) => void; placeholder: string;
}) {
  const [draft, setDraft] = useState("");
  const id = useRef(`chips-${label.replace(/\W+/g, "")}`).current;
  const add = () => { const next = draft.trim(); if (next) { onAdd(next); setDraft(""); } };
  return (
    <div className="set-field">
      <span>{label}</span>
      <ul className="set-chips">
        {items.map((item) => <li key={item}>[{item} <button type="button" aria-label={`Quitar ${item}`} onClick={() => onRemove(item)}>×</button>]</li>)}
        {items.length === 0 && <li className="set-empty">ninguno todavía</li>}
      </ul>
      <input value={draft} list={suggestions ? id : undefined} placeholder={placeholder} onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} onBlur={add} />
      {suggestions && <datalist id={id}>{suggestions.map((option) => <option key={option} value={option} />)}</datalist>}
    </div>
  );
}

export default function ProfileTab({ career, onError }: { career: Career; onError: (e: unknown) => void }) {
  const [me, setMe] = useState<MeProfile | null>(null);
  const [places, setPlaces] = useState<string[]>([]);
  const [toast, setToast] = useState<Toast | null>(null);
  const [version, setVersion] = useState(0);
  const [newSkill, setNewSkill] = useState("");
  const [newLevel, setNewLevel] = useState("basic");
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(() => api.me().then(setMe).catch(onError), [onError]);
  useEffect(() => {
    void load();
    api.places().then((c) => setPlaces(c.groups.flatMap((g) => g.places))).catch(() => undefined);
    return () => window.clearTimeout(timer.current);
  }, [load]);

  const flash = (next: Toast) => {
    window.clearTimeout(timer.current);
    setToast(next);
    timer.current = window.setTimeout(() => setToast(null), UNDO_MS);
  };
  const save = async (fields: Record<string, unknown>, isUndo = false) => {
    try {
      const result = await api.patchMe(fields);
      setMe(result.profile);
      if (result.changed.length) flash(isUndo ? { text: "Cambio deshecho", warnings: [] } : { text: "Guardado", undo: result.undo, warnings: result.warnings });
      else if (result.warnings.length) flash({ text: "Sin cambios", warnings: result.warnings });
    } catch (error) {
      onError(error);
      setVersion((current) => current + 1); // remonta los campos con el valor que sí quedó guardado
      void load();
    }
  };

  if (!me) return <p className="m-empty">Cargando…</p>;
  const skillNames = career.skills.filter((skill) => skill.type !== "soft").map((skill) => skill.name).filter((name) => !(name in me.skills));
  const areaOptions = [...career.areas.core, ...career.areas.adjacent].filter((area) => !me.areas.includes(area));
  const initials = me.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "?";
  const skillEntries = Object.entries(me.skills).filter(([, level]) => level !== "none");
  const toggleMode = (mode: string) => void save({ work_modes: me.work_modes.includes(mode) ? me.work_modes.filter((m) => m !== mode) : [...me.work_modes, mode] });

  return (
    <div className="set-profile" key={version}>
      <header className="set-identity">
        {/* eslint-disable-next-line @next/next/no-img-element -- export estático sin optimizador de imágenes */}
        {me.has_photo ? <img className="set-photo" src={CV_PHOTO_URL} alt={`Foto de ${me.name}`} /> : <div className="set-photo set-photo-empty" aria-hidden="true">{initials}</div>}
        <div className="set-identity-fields">
          <Field label="Nombre" value={me.name} maxLength={80} onCommit={(value) => void save({ name: value })} />
          <Field label="Titular" value={me.headline} maxLength={200} placeholder="Ej. Ingeniería Industrial · Datos y procesos" onCommit={(value) => void save({ headline: value })} />
          <Field label="Distrito donde vives" value={me.home_district} list="set-places" maxLength={60} placeholder="Radar mide la distancia a cada oferta desde aquí" onCommit={(value) => void save({ home_district: value })} />
        </div>
      </header>

      <div className="set-progress" role="status" aria-label={`Perfil completo al ${me.completeness.percent}%`}>
        <div className="set-progress-bar"><i style={{ width: `${me.completeness.percent}%` }} /></div>
        <p className="set-log">{me.completeness.percent === 100 ? "perfil completo" : `perfil ${me.completeness.percent}% — falta: ${me.completeness.missing.map((item) => item.label.toLowerCase()).join(", ")}`}</p>
        {me.completeness.missing.slice(0, 2).map((item) => <p key={item.key} className="set-why">{item.label}: {item.why}</p>)}
      </div>

      <section className="set-section">
        <h2>Sobre mí</h2>
        <Field label="Resumen (el párrafo «Perfil» de tu CV)" value={me.summary} multiline maxLength={600} onCommit={(value) => void save({ summary: value })} />
        <Field label="Formación en una línea" value={me.education} maxLength={300} onCommit={(value) => void save({ education: value })} />
      </section>

      <section className="set-section">
        <h2>Contacto</h2>
        <p className="m-sub">Aparece en el CV que descargas. No sale de tu equipo.</p>
        <div className="set-grid">
          {CONTACT.map(([key, label]) => <Field key={key} label={label} value={me.contact[key] ?? ""} maxLength={120} onCommit={(value) => void save({ contact: { [key]: value } })} />)}
        </div>
      </section>

      <section className="set-section">
        <h2>Qué buscas</h2>
        <Chips label="Áreas objetivo" items={me.areas} suggestions={areaOptions} placeholder="Añadir un área y Enter"
          onAdd={(value) => void save({ areas_add: [value] })} onRemove={(value) => void save({ areas_remove: [value] })} />
        <Chips label="Lugares donde buscas" items={me.locations} suggestions={places} placeholder="Añadir un distrito o ciudad y Enter"
          onAdd={(value) => void save({ locations_add: [value] })} onRemove={(value) => void save({ locations_remove: [value] })} />
        <div className="set-field">
          <span>Modalidad</span>
          <div className="set-modes" role="group" aria-label="Modalidad de trabajo">
            {MODES.map(([value, label]) => <button key={value} type="button" aria-pressed={me.work_modes.includes(value)} className={me.work_modes.includes(value) ? "active" : ""} onClick={() => toggleMode(value)}>{label}</button>)}
          </div>
        </div>
      </section>

      <section className="set-section">
        <h2>Skills <b>{skillEntries.length}</b></h2>
        <p className="m-sub">Tu nivel declarado alimenta el encaje y el plan de cierre. Lo que demuestres con proyectos o certificados se mide aparte, en CVs.</p>
        <ul className="set-skills">
          {skillEntries.map(([name, level]) => (
            <li key={name}>
              <span>{name}</span>
              <select value={level} aria-label={`Nivel de ${name}`} onChange={(e) => void save({ skills: { [name]: e.target.value } })}>
                {LEVELS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                {!LEVELS.some(([value]) => value === level) && <option value={level}>{LEVEL_LABEL[level] ?? level}</option>}
              </select>
              <button type="button" aria-label={`Quitar ${name}`} onClick={() => void save({ skills: { [name]: "remove" } })}>✕</button>
            </li>
          ))}
          {skillEntries.length === 0 && <li className="set-empty">Aún no declaraste ninguna.</li>}
        </ul>
        <form className="set-add-skill" onSubmit={(e) => { e.preventDefault(); const name = newSkill.trim(); if (name) { void save({ skills: { [name]: newLevel } }); setNewSkill(""); } }}>
          <input value={newSkill} list="set-skills" placeholder="Añadir una skill" onChange={(e) => setNewSkill(e.target.value)} />
          <select value={newLevel} aria-label="Nivel de la nueva skill" onChange={(e) => setNewLevel(e.target.value)}>{LEVELS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
          <button type="submit">Añadir</button>
        </form>
      </section>

      <p className="set-footnote">Experiencia, certificados y proyectos se editan en la vista <a href="/radar">CVs</a> o pidiéndoselo al agente. Todo lo de esta pantalla también lo puede cambiar el agente, con tu confirmación.</p>

      <datalist id="set-places">{places.map((place) => <option key={place} value={place} />)}</datalist>
      <datalist id="set-skills">{skillNames.map((name) => <option key={name} value={name} />)}</datalist>

      {toast && (
        <div className="set-toast" role="status">
          <span>{toast.text}{toast.warnings.length > 0 && ` · ${toast.warnings[0]}`}</span>
          {toast.undo && <button type="button" onClick={() => { const undo = toast.undo; setToast(null); if (undo) void save(undo, true); }}>Deshacer</button>}
        </div>
      )}
    </div>
  );
}
