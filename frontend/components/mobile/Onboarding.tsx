"use client";

import { useEffect, useState } from "react";
import { api, type Career } from "../../lib/mobile-api";

const LEVELS = [["none", "No"], ["basic", "Básico"], ["intermediate", "Medio"], ["advanced", "Alto"]] as const;
const MODES = [["presencial", "Presencial"], ["hybrid", "Híbrido"], ["remote", "Remoto"]] as const;

export default function Onboarding({ onDone, onError }: { onDone: () => void; onError: (e: unknown) => void }) {
  const [career, setCareer] = useState<Career | null>(null);
  const [name, setName] = useState("");
  const [education, setEducation] = useState("");
  const [locations, setLocations] = useState("Lima");
  const [modes, setModes] = useState<string[]>([]);
  const [areas, setAreas] = useState<string[]>([]);
  const [skills, setSkills] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { api.career().then(setCareer).catch(onError); }, [onError]);
  if (!career) return <p className="m-empty">Cargando…</p>;

  const changeCareer = async (id: string) => {
    try { setCareer(await api.setCareer(id)); setAreas([]); setSkills({}); } catch (error) { onError(error); }
  };
  const toggle = (list: string[], set: (v: string[]) => void, value: string) =>
    set(list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);
  const save = async () => {
    setSaving(true);
    try {
      await api.saveProfile({
        name: name.trim(), education: education.trim() || undefined, areas,
        locations: locations.split(",").map((s) => s.trim()).filter(Boolean), work_modes: modes,
        skills: Object.fromEntries(Object.entries(skills).filter(([, v]) => v !== "none")),
      });
      onDone();
    } catch (error) { onError(error); } finally { setSaving(false); }
  };
  const areaOptions = [...career.areas.core, ...career.areas.adjacent];

  return (
    <div className="m-stack">
      <header className="m-head"><span className="m-eyebrow">[INICIO]</span><h1>Bienvenido a Radar</h1><p>Tres minutos para que las ofertas se ordenen por ti. Solo declara lo que es cierto: nada se inventa.</p></header>
      <section className="m-card">
        <h2>1. Tu carrera</h2>
        <select value={career.active} onChange={(e) => changeCareer(e.target.value)} aria-label="Carrera">
          {career.tracks.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </section>
      <section className="m-card">
        <h2>2. Sobre ti</h2>
        <label>Nombre<input value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name" /></label>
        <label>Formación<input value={education} onChange={(e) => setEducation(e.target.value)} placeholder="Ej.: Estudiante de 8.º ciclo" /></label>
        <label>Distritos o ciudades (separados por coma)<input value={locations} onChange={(e) => setLocations(e.target.value)} /></label>
        <div className="m-chips m-wrap" aria-label="Modalidad">
          {MODES.map(([value, label]) => <button key={value} aria-pressed={modes.includes(value)} onClick={() => toggle(modes, setModes, value)}>{label}</button>)}
        </div>
      </section>
      <section className="m-card">
        <h2>3. Áreas que buscas</h2>
        <div className="m-chips m-wrap">
          {areaOptions.map((a) => <button key={a} aria-pressed={areas.includes(a)} onClick={() => toggle(areas, setAreas, a)}>{a}</button>)}
        </div>
      </section>
      <section className="m-card">
        <h2>4. Tus skills</h2>
        <ul className="m-skills">
          {career.skills.map((s) => (
            <li key={s.name}>
              <span>{s.name}</span>
              <div className="m-seg" role="group" aria-label={`Nivel de ${s.name}`}>
                {LEVELS.map(([value, label]) => <button key={value} aria-pressed={(skills[s.name] ?? "none") === value} onClick={() => setSkills({ ...skills, [s.name]: value })}>{label}</button>)}
              </div>
            </li>
          ))}
        </ul>
      </section>
      <button className="m-primary" disabled={!name.trim() || saving} onClick={save}>{saving ? "Guardando…" : "Ver mis ofertas"}</button>
    </div>
  );
}
