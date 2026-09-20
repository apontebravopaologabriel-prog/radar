"use client";

import { useEffect, useState } from "react";
import { api, type Career } from "../../lib/mobile-api";
import CustomCareerForm from "./CustomCareerForm";
import RefreshPanel from "./RefreshPanel";

const LEVELS = [["none", "No"], ["basic", "Básico"], ["intermediate", "Medio"], ["advanced", "Alto"]] as const;
const MODES = [["presencial", "Presencial"], ["hybrid", "Híbrido"], ["remote", "Remoto"]] as const;

export default function Onboarding({ onDone, onError }: { onDone: () => void; onError: (e: unknown) => void }) {
  const [career, setCareer] = useState<Career | null>(null);
  const [places, setPlaces] = useState<string[]>([]);
  const [custom, setCustom] = useState(false);
  const [name, setName] = useState("");
  const [education, setEducation] = useState("");
  const [locations, setLocations] = useState("Lima");
  const [modes, setModes] = useState<string[]>([]);
  const [areas, setAreas] = useState<string[]>([]);
  const [skills, setSkills] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.career().then(setCareer).catch(onError);
    api.places().then((c) => setPlaces(c.groups.flatMap((g) => g.places))).catch(() => undefined);
  }, [onError]);
  if (!career) return <p className="m-empty">Cargando…</p>;

  const changeCareer = async (id: string) => {
    try { setCareer(await api.setCareer(id)); setAreas([]); setSkills({}); } catch (error) { onError(error); }
  };
  const toggle = (list: string[], set: (v: string[]) => void, value: string) =>
    set(list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);
  const placeList = locations.split(",").map((s) => s.trim()).filter(Boolean);
  const save = async () => {
    setSaving(true);
    try {
      await api.saveProfile({
        name: name.trim(), education: education.trim() || undefined, areas,
        locations: placeList, work_modes: modes,
        skills: Object.fromEntries(Object.entries(skills).filter(([, v]) => v !== "none")),
      });
      setSaved(true);
    } catch (error) { onError(error); } finally { setSaving(false); }
  };
  const areaOptions = [...career.areas.core, ...career.areas.adjacent];

  if (saved) {
    return (
      <div className="m-stack">
        <header className="m-head"><span className="m-eyebrow">[LISTO]</span><h1>Todo listo, {name.trim()}</h1><p>Ahora Radar puede traer ofertas de {career.name} para {placeList.join(", ") || "Lima"}.</p></header>
        <section className="m-card">
          <h2>Traer ofertas ahora</h2>
          <p className="m-sub">Busca en Computrabajo (y en Indeed/LinkedIn si están instalados) y ordena todo por tu perfil. Tarda unos minutos y puedes seguir usando Radar.</p>
          <RefreshPanel places={placeList} onError={onError} />
        </section>
        <button className="m-primary" onClick={onDone}>Ver mis ofertas</button>
      </div>
    );
  }
  return (
    <div className="m-stack">
      <header className="m-head"><span className="m-eyebrow">[INICIO]</span><h1>Bienvenido a Radar</h1><p>Unas preguntas para estudiar el trabajo en el Perú desde tu carrera. Empezamos por Lima. Solo declara lo que es cierto: nada se inventa.</p></header>
      <section className="m-card">
        <h2>1. Tu carrera</h2>
        <select value={custom ? "__custom" : career.active} onChange={(e) => e.target.value === "__custom" ? setCustom(true) : (setCustom(false), void changeCareer(e.target.value))} aria-label="Carrera">
          {career.tracks.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          <option value="__custom">Mi carrera no está en la lista…</option>
        </select>
        {custom && <CustomCareerForm onError={onError} onCreated={(c) => { setCareer(c); setCustom(false); setAreas([]); setSkills({}); }} />}
      </section>
      <section className="m-card">
        <h2>2. Sobre ti</h2>
        <label>Nombre<input value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name" /></label>
        <label>Formación<input value={education} onChange={(e) => setEducation(e.target.value)} placeholder="Ej.: Estudiante de 8.º ciclo" /></label>
        <label>Dónde buscas (distritos o ciudades, separados por coma)
          <input value={locations} onChange={(e) => setLocations(e.target.value)} list="radar-places" />
          <datalist id="radar-places">{places.map((p) => <option key={p} value={p} />)}</datalist>
        </label>
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
      <button className="m-primary" disabled={!name.trim() || saving} onClick={save}>{saving ? "Guardando…" : "Guardar perfil"}</button>
    </div>
  );
}
