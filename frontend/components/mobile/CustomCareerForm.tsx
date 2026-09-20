"use client";

import { useState } from "react";
import { api, type Career } from "../../lib/mobile-api";

const EXAMPLE = "Emergencias: triaje, urgencias\nCuidados intensivos: uci, ventilación";

/** Crea una carrera propia: áreas con palabras clave y skills. Se guarda en el equipo del usuario. */
export default function CustomCareerForm({ onCreated, onError }: { onCreated: (career: Career) => void; onError: (e: unknown) => void }) {
  const [name, setName] = useState("");
  const [areasText, setAreasText] = useState("");
  const [skillsText, setSkillsText] = useState("");
  const [saving, setSaving] = useState(false);

  const parse = (): Record<string, string[]> => {
    const areas: Record<string, string[]> = {};
    for (const line of areasText.split("\n")) {
      const [area, rest] = line.split(":");
      if (!area?.trim()) continue;
      areas[area.trim()] = (rest ?? "").split(",").map((k) => k.trim()).filter(Boolean);
    }
    return areas;
  };
  const areas = parse();
  const submit = async () => {
    setSaving(true);
    try {
      onCreated(await api.createCustomCareer({ name: name.trim(), areas, skills: skillsText.split(",").map((s) => s.trim()).filter(Boolean) }));
    } catch (error) { onError(error); } finally { setSaving(false); }
  };
  return (
    <div className="m-custom">
      <p className="m-sub">Dinos qué áreas de trabajo te interesan y con qué palabras aparecen en las ofertas. Se guarda solo en tu equipo.</p>
      <label>Nombre de tu carrera<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ej.: Enfermería" /></label>
      <label>Áreas (una por línea, «Área: palabra, palabra»)
        <textarea value={areasText} onChange={(e) => setAreasText(e.target.value)} rows={4} placeholder={EXAMPLE} />
      </label>
      <label>Skills a buscar (separadas por coma)<input value={skillsText} onChange={(e) => setSkillsText(e.target.value)} placeholder="Ej.: BLS, Manejo de bombas de infusión" /></label>
      <button className="m-primary" disabled={!name.trim() || Object.keys(areas).length === 0 || saving} onClick={submit}>{saving ? "Guardando…" : "Crear mi carrera"}</button>
    </div>
  );
}
