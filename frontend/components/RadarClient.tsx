"use client";

import dynamic from "next/dynamic";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { fetchJobs } from "../lib/api";
import { districtKey } from "../lib/districts";
import type { DistrictSummary, Filters, Job, MapMode } from "../types";

const MapView = dynamic(() => import("./MapView"), { ssr: false, loading: () => <div className="map-loading">Cargando mapa de Lima…</div> });

const AREAS = ["", "Operaciones", "Producción", "Mejora continua", "Procesos", "Supply Chain", "Logística", "Compras", "Planeamiento", "Demand Planning", "Calidad", "Data / BI", "Analytics", "Automatización", "Proyectos / PMO", "Finanzas / Control de gestión", "Seguridad y Salud en el Trabajo", "Recursos Humanos / People Analytics"];
const INITIAL_FILTERS: Filters = { search: "", area: "", seniority: "", work_mode: "", min_salary: "", max_age_days: "14" };
const RADAR_RADII = [2, 5, 10] as const;

function formatDate(value: string | null) {
  if (!value) return "Fecha no indicada";
  return new Intl.DateTimeFormat("es-PE", { day: "2-digit", month: "short" }).format(new Date(value));
}

function formatSalary(job: Job) {
  if (job.salary_min === null && job.salary_max === null) return "No indicado";
  const currency = job.salary_currency === "PEN" ? "S/" : job.salary_currency || "";
  if (job.salary_min !== null && job.salary_max !== null) return `${currency} ${job.salary_min.toLocaleString("es-PE")} – ${job.salary_max.toLocaleString("es-PE")}`;
  return `${currency} ${(job.salary_min ?? job.salary_max)?.toLocaleString("es-PE")}`;
}

function distanceKm(from: { latitude: number; longitude: number }, to: { latitude: number; longitude: number }) {
  const earthRadiusKm = 6371;
  const latDelta = ((to.latitude - from.latitude) * Math.PI) / 180;
  const lonDelta = ((to.longitude - from.longitude) * Math.PI) / 180;
  const latitudeA = (from.latitude * Math.PI) / 180;
  const latitudeB = (to.latitude * Math.PI) / 180;
  const a = Math.sin(latDelta / 2) ** 2 + Math.cos(latitudeA) * Math.cos(latitudeB) * Math.sin(lonDelta / 2) ** 2;
  return 2 * earthRadiusKm * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export default function RadarClient() {
  const [filters, setFilters] = useState<Filters>(INITIAL_FILTERS);
  const [draftSearch, setDraftSearch] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<MapMode>("heatmap");
  const [selectedDistrictKey, setSelectedDistrictKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [radarCenter, setRadarCenter] = useState({ longitude: -77.043, latitude: -12.046 });
  const [radarRadiusKm, setRadarRadiusKm] = useState<number>(5);
  const [radarDistrictKey, setRadarDistrictKey] = useState<string | null>(null);
  const selectedJob = useMemo(() => jobs.find((job) => job.id === selectedId) || null, [jobs, selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchJobs(filters, controller.signal)
      .then((result) => setJobs(result))
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError("No se pudo conectar con Radar API. Inicia `radar-api` y vuelve a cargar.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [filters]);

  const mappedCount = jobs.filter((job) => job.latitude !== null && job.longitude !== null).length;
  const districtStats = useMemo<DistrictSummary[]>(() => {
    const groups = new Map<string, DistrictSummary>();
    for (const job of jobs) {
      const key = districtKey(job.district);
      if (!key || job.latitude === null || job.longitude === null) continue;
      const current = groups.get(key);
      if (current) {
        current.count += 1;
        current.latitude = (current.latitude * (current.count - 1) + job.latitude) / current.count;
        current.longitude = (current.longitude * (current.count - 1) + job.longitude) / current.count;
      } else {
        groups.set(key, { key, district: job.district as string, count: 1, latitude: job.latitude, longitude: job.longitude });
      }
    }
    return [...groups.values()].sort((a, b) => b.count - a.count || a.district.localeCompare(b.district));
  }, [jobs]);
  const visibleJobs = useMemo(
    () => {
      if (mode === "radar") {
        if (!radarDistrictKey) return [];
        return jobs.filter((job) => job.latitude !== null && job.longitude !== null && distanceKm(radarCenter, { latitude: job.latitude, longitude: job.longitude }) <= radarRadiusKm);
      }
      return selectedDistrictKey ? jobs.filter((job) => districtKey(job.district) === selectedDistrictKey) : jobs;
    },
    [jobs, mode, radarCenter, radarRadiusKm, selectedDistrictKey],
  );
  const selectedDistrict = districtStats.find((district) => district.key === selectedDistrictKey) || null;
  const radarDistrict = districtStats.find((district) => district.key === radarDistrictKey) || null;
  const radarRadiusCounts = useMemo(
    () => RADAR_RADII.map((radius) => ({ radius, count: radarDistrictKey ? jobs.filter((job) => job.latitude !== null && job.longitude !== null && distanceKm(radarCenter, { latitude: job.latitude, longitude: job.longitude }) <= radius).length : 0 })),
    [jobs, radarCenter, radarDistrictKey],
  );

  useEffect(() => {
    if (selectedDistrictKey && !districtStats.some((district) => district.key === selectedDistrictKey)) {
      setSelectedDistrictKey(null);
    }
  }, [districtStats, selectedDistrictKey]);

  useEffect(() => {
    if (mode !== "radar" || !radarDistrictKey || districtStats.some((district) => district.key === radarDistrictKey)) return;
    setRadarDistrictKey(null);
    setRadarCenter({ longitude: -77.043, latitude: -12.046 });
  }, [districtStats, mode, radarDistrictKey]);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters((current) => ({ ...current, search: draftSearch.trim() }));
  }

  function updateFilter(key: keyof Filters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function selectJob(job: Job) {
    setSelectedId(job.id);
    if (mode === "heatmap") setSelectedDistrictKey(districtKey(job.district));
  }

  function selectDistrict(key: string) {
    setSelectedDistrictKey(key);
    setSelectedId(null);
  }

  function selectRadarDistrict(key: string) {
    const district = districtStats.find((item) => item.key === key);
    if (!district) return;
    setRadarDistrictKey(key);
    setRadarCenter({ longitude: district.longitude, latitude: district.latitude });
    setSelectedId(null);
  }

  function changeMode(nextMode: MapMode) {
    setMode(nextMode);
    setSelectedId(null);
    if (nextMode !== "heatmap") setSelectedDistrictKey(null);
    if (nextMode === "radar") {
      setRadarDistrictKey(null);
      setRadarCenter({ longitude: -77.043, latitude: -12.046 });
    }
  }

  return (
    <main className="radar-shell">
      <header className="topbar">
        <div className="brand-lockup"><span className="brand-mark">⌁</span><div><strong>RADAR</strong><span>Career intelligence</span></div></div>
        <div className="topbar-context"><span className="live-dot" /> Mercado activo · Lima</div>
        <div className="topbar-actions"><button className="icon-button" aria-label="Ayuda">?</button><div className="avatar">P</div></div>
      </header>

      <section className="workspace">
        <aside className="sidebar">
          <div className="sidebar-heading"><div><p className="eyebrow">Explorador</p><h1>Mapa de oportunidades</h1></div><span className="result-count">{visibleJobs.length}</span></div>
          <form className="search-box" onSubmit={submitSearch}><span>⌕</span><input value={draftSearch} onChange={(event) => setDraftSearch(event.target.value)} placeholder="Buscar cargo, skill o empresa" /><button type="submit" aria-label="Buscar">↵</button></form>

          <div className="filter-section"><div className="section-label">Filtros activos <span>{Object.values(filters).filter(Boolean).length}</span></div>
            <label>Área profesional<select value={filters.area} onChange={(event) => updateFilter("area", event.target.value)}>{AREAS.map((area) => <option key={area} value={area}>{area || "Todas las áreas"}</option>)}</select></label>
            <div className="two-columns"><label>Seniority<select value={filters.seniority} onChange={(event) => updateFilter("seniority", event.target.value)}><option value="">Todos</option><option value="intern">Practicante</option><option value="junior">Junior</option><option value="mid">Intermedio</option><option value="senior">Senior</option></select></label><label>Modalidad<select value={filters.work_mode} onChange={(event) => updateFilter("work_mode", event.target.value)}><option value="">Todas</option><option value="onsite">Presencial</option><option value="hybrid">Híbrido</option><option value="remote">Remoto</option></select></label></div>
            <div className="two-columns"><label>Salario mínimo<input type="number" min="0" placeholder="S/" value={filters.min_salary} onChange={(event) => updateFilter("min_salary", event.target.value)} /></label><label>Antigüedad<select value={filters.max_age_days} onChange={(event) => updateFilter("max_age_days", event.target.value)}><option value="7">7 días</option><option value="14">14 días</option><option value="30">30 días</option><option value="90">90 días</option></select></label></div>
          </div>

          <div className="map-mode"><div className="section-label">Visualización</div><div className="segmented">{([["heatmap", "Distritos"], ["radar", "Radar"]] as const).map(([value, label]) => <button key={value} className={mode === value ? "active" : ""} onClick={() => changeMode(value)} type="button">{label}</button>)}</div>{mode === "radar" && <div className="radar-controls"><label className="radar-center-control">Centro del radar<select value={radarDistrictKey || ""} onChange={(event) => selectRadarDistrict(event.target.value)}><option value="" disabled>Selecciona un distrito</option>{districtStats.map((district) => <option key={district.key} value={district.key}>{district.district} · {district.count} ofertas</option>)}</select></label><span className="radar-readout">CENTER // {radarDistrict?.district || "LIMA"} · RANGE // {radarRadiusKm} KM · {visibleJobs.length} MATCHES</span><div className="radar-radius">{radarRadiusCounts.map(({ radius, count }) => <button key={radius} className={radarRadiusKm === radius ? "active" : ""} type="button" onClick={() => { setRadarRadiusKm(radius); setSelectedId(null); }}><strong>{radius} KM</strong><span>{count} ofertas</span></button>)}</div></div>}</div>
          {mode === "heatmap" && districtStats.length > 0 && <div className="district-ranking"><div className="section-label">Distritos con más oportunidades</div><div className="district-ranking-list">{districtStats.slice(0, 6).map((district) => <button key={district.key} className={`district-row ${selectedDistrictKey === district.key ? "selected" : ""}`} onClick={() => selectDistrict(district.key)} type="button"><span className="district-row-top"><strong>{district.district}</strong><span>{district.count}</span></span><span className="district-bar"><i style={{ width: `${Math.max(10, (district.count / districtStats[0].count) * 100)}%` }} /></span></button>)}</div></div>}

          <div className="job-list-header"><span>{selectedDistrict ? `Ofertas en ${selectedDistrict.district}` : "Ofertas recientes"}</span><span>{loading ? "…" : `${visibleJobs.filter((job) => job.latitude !== null && job.longitude !== null).length} en mapa`}</span></div>
          <div className="job-list">{loading && <div className="empty-state">Buscando ofertas…</div>}{!loading && error && <div className="empty-state error-state">{error}</div>}{!loading && !error && visibleJobs.length === 0 && <div className="empty-state">No hay ofertas con estos filtros.</div>}{visibleJobs.map((job) => <button key={job.id} className={`job-card ${selectedId === job.id ? "selected" : ""}`} onClick={() => selectJob(job)}><div className="job-card-top"><span className="job-area">{job.primary_area || "Sin área"}</span><span className="job-date">{formatDate(job.published_at)}</span></div><strong>{job.title}</strong><span className="job-company">{job.company || "Empresa no indicada"}</span><div className="job-meta"><span>⌖ {job.district || job.location || "Ubicación pendiente"}</span><span>{job.work_mode === "hybrid" ? "Híbrido" : job.work_mode === "remote" ? "Remoto" : job.work_mode === "onsite" ? "Presencial" : "Modalidad n/i"}</span></div></button>)}</div>
        </aside>

        <section className="map-panel">
          <div className="map-header">
            <div>
              <p className="eyebrow">Vista geográfica</p>
              <h2>{mode === "heatmap" && selectedDistrict ? selectedDistrict.district : mode === "heatmap" ? "Concentración por distrito" : mode === "radar" ? `Radar${radarDistrict ? ` · ${radarDistrict.district}` : ""}` : "Lima Metropolitana"}</h2>
            </div>
            <div className="map-legend">
              {mode === "heatmap" ? <><span><i className="legend-scale low" /> Pocas ofertas</span><span><i className="legend-scale high" /> Más ofertas</span></> : <><span><i className="legend-dot" /> Oferta cercana</span><span><i className="legend-cluster" /> Concentración</span></>}
              {mode === "radar" && <span><i className="legend-ring" /> Radio activo</span>}
            </div>
          </div>
          <div className={`map-wrap ${mode === "radar" ? "radar-active" : ""}`}>
            <MapView jobs={visibleJobs} mode={mode} radarCenter={radarCenter} radarRadiusKm={radarRadiusKm} radarDistrictKey={radarDistrictKey} selectedDistrictKey={selectedDistrictKey} onSelectJob={(jobId) => { const job = visibleJobs.find((item) => item.id === jobId); if (job) selectJob(job); }} onSelectDistrict={selectDistrict} />
            {selectedJob && <article className="job-popover"><button className="close-button" onClick={() => setSelectedId(null)} aria-label="Cerrar detalle" type="button">×</button><span className="job-area">{selectedJob.primary_area || "Sin área"}</span><h3>{selectedJob.title}</h3><p className="popover-company">{selectedJob.company || "Empresa no indicada"}</p><div className="popover-divider" /><div className="popover-grid"><div><span>Ubicación</span><strong>{selectedJob.district || selectedJob.location || "Pendiente"}</strong></div><div><span>Modalidad</span><strong>{selectedJob.work_mode === "hybrid" ? "Híbrido" : selectedJob.work_mode === "remote" ? "Remoto" : selectedJob.work_mode === "onsite" ? "Presencial" : "No indicada"}</strong></div><div><span>Salario</span><strong>{formatSalary(selectedJob)}</strong></div><div><span>Publicado</span><strong>{formatDate(selectedJob.published_at)}</strong></div></div>{selectedJob.description && <p className="popover-description">{selectedJob.description}</p>}{selectedJob.url && <a className="popover-link" href={selectedJob.url} target="_blank" rel="noreferrer">Abrir oferta original ↗</a>}</article>}
          </div>
        </section>

      </section>
      <footer className="statusbar"><span><i className="status-dot" /> API Radar conectada</span><span>Fuente de verdad: PostgreSQL</span><span>Actualización: últimas {filters.max_age_days} días</span></footer>
    </main>
  );
}
