"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Nearby, type NearbyJob } from "../../lib/mobile-api";

const RADII = [2, 5, 10, 20];
const KEY = "radar.nearby.v1";

export default function NearbyView({ onError }: { onError: (e: unknown) => void }) {
  const [districts, setDistricts] = useState<string[]>([]);
  const [district, setDistrict] = useState("");
  const [radius, setRadius] = useState(5);
  const [data, setData] = useState<Nearby | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.districts().then(({ districts: list, default: fallback }) => {
      setDistricts(list);
      let saved: { district?: string; radius?: number } = {};
      try { saved = JSON.parse(localStorage.getItem(KEY) ?? "{}"); } catch { /* sin almacenamiento */ }
      setDistrict(saved.district && list.includes(saved.district) ? saved.district : fallback ?? list[0] ?? "");
      if (saved.radius && RADII.includes(saved.radius)) setRadius(saved.radius);
    }).catch(onError);
  }, [onError]);

  const load = useCallback(async () => {
    if (!district) return;
    setLoading(true);
    try {
      setData(await api.nearby(district, radius));
      try { localStorage.setItem(KEY, JSON.stringify({ district, radius })); } catch { /* sin almacenamiento */ }
    } catch (error) { onError(error); } finally { setLoading(false); }
  }, [district, radius, onError]);
  useEffect(() => { void load(); }, [load]);

  const star = async (job: NearbyJob) => {
    try {
      await api.favorite(job.id, !job.is_favorite);
      setData((d) => d && { ...d, jobs: d.jobs.map((j) => j.id === job.id ? { ...j, is_favorite: !j.is_favorite } : j) });
    } catch (error) { onError(error); }
  };
  const save = async (job: NearbyJob) => {
    try { await api.setApplication(job.id, "saved"); } catch (error) { onError(error); }
  };

  return (
    <div className="m-stack">
      <header className="m-head"><span className="m-eyebrow">[CERCA]</span><h1>Cerca de ti</h1><p>Ofertas por distancia, sin cargar el mapa</p></header>
      <label>Distrito de referencia
        <select value={district} onChange={(e) => setDistrict(e.target.value)} aria-label="Distrito">
          {districts.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </label>
      <div className="m-chips" role="group" aria-label="Radio">
        {RADII.map((r) => <button key={r} aria-pressed={radius === r} onClick={() => setRadius(r)}>{r} km</button>)}
      </div>
      {loading && !data && <p className="m-empty">Buscando…</p>}
      {data && (
        <>
          <p className="m-sub">{data.total} {data.total === 1 ? "oferta" : "ofertas"} a {data.radius_km} km de {data.origin} · {data.precision}</p>
          {data.jobs.length === 0 && <p className="m-empty">Nada en este radio. Prueba uno mayor.</p>}
          {data.jobs.map((job) => (
            <article className="m-card" key={job.id}>
              <div className="m-card-top">
                <div><h2>{job.title}</h2><p className="m-sub">{[job.company, job.district].filter(Boolean).join(" · ")}</p></div>
                <span className="m-km">{job.km === 0 ? "aquí" : `${job.km} km`}</span>
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
