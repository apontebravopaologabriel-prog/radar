"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import { api, type MapPlaces, type Nearby, type NearbyJob } from "../../lib/mobile-api";

const PlacesMap = dynamic(() => import("./PlacesMap"), { ssr: false, loading: () => <div className="m-map m-map-loading">Cargando mapa…</div> });

const RADII: [number, string][] = [[2, "2 km"], [5, "5 km"], [10, "10 km"], [25, "25 km"], [100, "100 km"], [2500, "Todo Perú"]];
const KEY = "radar.map.v1";

export default function MapTab({ onError }: { onError: (e: unknown) => void }) {
  const [groups, setGroups] = useState<{ label: string; places: string[] }[]>([]);
  const [place, setPlace] = useState("");
  const [radius, setRadius] = useState(10);
  const [points, setPoints] = useState<MapPlaces | null>(null);
  const [data, setData] = useState<Nearby | null>(null);
  const [tall, setTall] = useState(false);

  useEffect(() => {
    Promise.all([api.places(), api.mapPlaces()]).then(([catalog, map]) => {
      setGroups(catalog.groups); setPoints(map);
      let saved: { place?: string; radius?: number } = {};
      try { saved = JSON.parse(localStorage.getItem(KEY) ?? "{}"); } catch { /* sin almacenamiento */ }
      const all = catalog.groups.flatMap((g) => g.places);
      setPlace(saved.place && all.includes(saved.place) ? saved.place : catalog.default ?? map.places[0]?.name ?? all[0] ?? "");
      if (saved.radius && RADII.some(([r]) => r === saved.radius)) setRadius(saved.radius);
    }).catch(onError);
  }, [onError]);

  const load = useCallback(async () => {
    if (!place) return;
    try {
      setData(await api.nearby(place, radius));
      try { localStorage.setItem(KEY, JSON.stringify({ place, radius })); } catch { /* sin almacenamiento */ }
    } catch (error) { onError(error); }
  }, [place, radius, onError]);
  useEffect(() => { void load(); }, [load]);

  const star = async (job: NearbyJob) => {
    try {
      await api.favorite(job.id, !job.is_favorite);
      setData((d) => d && { ...d, jobs: d.jobs.map((j) => j.id === job.id ? { ...j, is_favorite: !j.is_favorite } : j) });
    } catch (error) { onError(error); }
  };
  const save = async (job: NearbyJob) => { try { await api.setApplication(job.id, "saved"); } catch (error) { onError(error); } };

  const height = typeof window === "undefined" ? 320 : Math.round(window.innerHeight * (tall ? 0.62 : 0.4));
  return (
    <div className="m-stack">
      <header className="m-head"><span className="m-eyebrow">[MAPA]</span><h1>Mapa</h1>
        <p>{points ? `${points.total} ofertas en ${points.places.length} lugares del Perú` : "Cargando…"}</p></header>
      <PlacesMap places={points?.places ?? []} selected={place} radiusKm={radius} height={height} onSelect={setPlace} />
      <div className="m-actions m-map-tools">
        <button onClick={() => setTall(!tall)}>{tall ? "Reducir mapa" : "Ampliar mapa"}</button>
        <span className="m-sub">Toca un punto para elegir el lugar. Punteado = solo se sabe el departamento.</span>
      </div>
      <label>Lugar de referencia
        <select value={place} onChange={(e) => setPlace(e.target.value)} aria-label="Lugar">
          {groups.map((g) => <optgroup key={g.label} label={g.label}>{g.places.map((p) => <option key={p} value={p}>{p}</option>)}</optgroup>)}
        </select>
      </label>
      <div className="m-chips" role="group" aria-label="Radio">
        {RADII.map(([r, label]) => <button key={r} aria-pressed={radius === r} onClick={() => setRadius(r)}>{label}</button>)}
      </div>
      {data && (
        <>
          <p className="m-sub">{data.total} {data.total === 1 ? "oferta" : "ofertas"} {radius >= 2500 ? "en todo el Perú" : `a ${data.radius_km} km`}, desde {data.origin} · {data.precision}</p>
          {data.jobs.length === 0 && <p className="m-empty">Nada en este radio. Prueba uno mayor.</p>}
          {data.jobs.map((job) => (
            <article className="m-card" key={job.id}>
              <div className="m-card-top">
                <div><h2>{job.title}</h2><p className="m-sub">{[job.company, job.place].filter(Boolean).join(" · ")}</p></div>
                <span className="m-km">{job.precision === "department" ? "dpto." : job.km === 0 ? "aquí" : `${Math.round(job.km)} km`}</span>
              </div>
              <div className="m-actions">
                <button onClick={() => save(job)}>Guardar</button>
                <button aria-pressed={job.is_favorite} onClick={() => star(job)}>{job.is_favorite ? "★" : "☆"}</button>
                {job.url && <a href={job.url} target="_blank" rel="noopener noreferrer">Abrir ↗</a>}
              </div>
            </article>
          ))}
        </>
      )}
    </div>
  );
}
