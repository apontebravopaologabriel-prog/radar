"use client";

import { useEffect, useState } from "react";
import { fetchMarkets, fetchSearchProfile, saveSearchProfile, type Market, type SearchPreferences } from "../lib/markets-api";
import "./market-controls.css";

const splitLines = (value: string) => [...new Set(value.split("\n").map((line) => line.trim()).filter(Boolean))];
export default function MarketProfileEditor() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [market, setMarket] = useState("industrial_engineering");
  const [preferences, setPreferences] = useState<SearchPreferences>({});
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetchMarkets(controller.signal).then(({ markets: choices }) => {
      setMarkets(choices);
      try {
        const selected = localStorage.getItem("radar.market");
        if (selected && choices.some((choice) => choice.id === selected)) setMarket(selected);
      } catch { /* Storage is optional. */ }
    }).catch((error) => { if (!controller.signal.aborted) setMessage(error.message); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setLoaded(false); setMessage(""); setPreferences({});
    fetchSearchProfile(market, controller.signal).then((profile) => {
      if (!controller.signal.aborted) { setPreferences(profile.preferences); setLoaded(true); }
    }).catch((error) => { if (!controller.signal.aborted) setMessage(error.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [market]);
  const current = markets.find((choice) => choice.id === market);
  const setField = (key: keyof SearchPreferences, values: string[]) => setPreferences((previous) => ({ ...previous, [key]: values }));
  async function save() {
    setSaving(true); setMessage("");
    try { await saveSearchProfile(market, preferences); setMessage("Búsqueda guardada. Actívala en Filtros → Perfil de búsqueda."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "No se pudo guardar"); }
    finally { setSaving(false); }
  }
  return <section className="set-section" id="mercados">
    <h2>Perfiles de búsqueda por mercado</h2>
    <p className="m-sub">Cada mercado conserva sus preferencias. Tu formación, experiencia y habilidades reales se comparten. Los campos vacíos no restringen la búsqueda.</p>
    <label>Mercado<select value={market} disabled={saving || !markets.length} onChange={(e) => setMarket(e.target.value)}>
      {markets.map((choice) => <option key={choice.id} value={choice.id}>{choice.name}</option>)}
    </select></label>
    {loading ? <p role="status">Cargando preferencias…</p> : loaded ? <fieldset className="market-profile-fields" disabled={saving}>
      <label>Áreas de interés (selección múltiple)<select multiple value={preferences.areas || []} onChange={(e) => setField("areas", Array.from(e.target.selectedOptions, (option) => option.value))}>
        {[...new Set([...(current?.areas.core || []), ...(current?.areas.adjacent || []), ...(preferences.areas || [])])].map((area) => <option key={area} value={area}>{area}</option>)}
      </select></label>
      <button type="button" onClick={() => setField("areas", [])}>Usar todas las áreas</button>
      {([["roles", "Puestos de interés", "Analista de datos\nAnalista de operaciones"], ["locations", "Ubicaciones", "Lima\nArequipa"], ["excluded_titles", "Títulos que quieres excluir", "Ventas\nCall center"]] as const).map(([key, label, placeholder]) =>
        <label key={key}>{label} · uno por línea<textarea value={(preferences[key] || []).join("\n")} placeholder={placeholder} onChange={(e) => setField(key, e.target.value.split("\n"))} onBlur={(e) => setField(key, splitLines(e.target.value))} /></label>)}
      <label>Seniority<select multiple value={preferences.seniority || []} onChange={(e) => setField("seniority", Array.from(e.target.selectedOptions, (option) => option.value))}>
        <option value="intern">Practicante</option><option value="junior">Junior</option><option value="mid">Intermedio</option><option value="senior">Senior</option>
      </select></label>
      <label>Modalidad<select multiple value={preferences.work_modes || []} onChange={(e) => setField("work_modes", Array.from(e.target.selectedOptions, (option) => option.value))}>
        <option value="onsite">Presencial</option><option value="hybrid">Híbrido</option><option value="remote">Remoto</option>
      </select></label>
      <button type="button" onClick={() => { setField("seniority", []); setField("work_modes", []); }}>Cualquier seniority y modalidad</button>
      <button type="button" className="m-primary" onClick={() => void save()}>{saving ? "Guardando…" : "Guardar búsqueda de este mercado"}</button>
    </fieldset> : null}
    {message && <p role="status">{message}</p>}
  </section>;
}
