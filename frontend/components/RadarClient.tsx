"use client";

import dynamic from "next/dynamic";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { fetchFavoriteJobs, fetchHiddenJobs, fetchJobs, fetchSkillOverview, updateJobFavorite, updateJobStatus } from "../lib/api";
import { districtKey } from "../lib/districts";
import type { DistrictSummary, Filters, Job, MapMode, SkillOverview } from "../types";
import SkillsView from "./SkillsView";

const MapView = dynamic(() => import("./MapView"), { ssr: false, loading: () => <div className="map-loading">Cargando mapa de Lima…</div> });

const AREAS = ["", "Operaciones", "Producción", "Mejora continua", "Procesos", "Supply Chain", "Logística", "Compras", "Planeamiento", "Demand Planning", "Calidad", "Data / BI", "Analytics", "Automatización", "Proyectos / PMO", "Finanzas / Control de gestión", "Seguridad y Salud en el Trabajo", "Recursos Humanos / People Analytics"];
const INITIAL_FILTERS: Filters = { search: "", area: "", seniority: "", work_mode: "", min_salary: "", max_age_days: "7" };
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

function sourceLabel(url: string | null) {
  if (!url) return "Abrir oferta original";
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (host.includes("linkedin")) return "Ver en LinkedIn";
    if (host.includes("indeed")) return "Ver en Indeed";
    if (host.includes("computrabajo")) return "Ver en Computrabajo";
    if (host.includes("glassdoor")) return "Ver en Glassdoor";
  } catch {
    return "Abrir oferta original";
  }
  return "Ver oferta original";
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
  const [hiddenJobs, setHiddenJobs] = useState<Job[]>([]);
  const [favoriteJobs, setFavoriteJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<MapMode>("heatmap");
  const [selectedDistrictKey, setSelectedDistrictKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [skillOverview, setSkillOverview] = useState<SkillOverview | null>(null);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState<string | null>(null);
  const [radarCenter, setRadarCenter] = useState({ longitude: -77.043, latitude: -12.046 });
  const [radarRadiusKm, setRadarRadiusKm] = useState<number>(5);
  const [radarDistrictKey, setRadarDistrictKey] = useState<string | null>(null);
  const [radarCenterOpen, setRadarCenterOpen] = useState(false);
  const [showAllDistricts, setShowAllDistricts] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [showFavorites, setShowFavorites] = useState(false);
  const [hideReasonFor, setHideReasonFor] = useState<string | null>(null);
  const [hideReason, setHideReason] = useState("");
  const [statusBusy, setStatusBusy] = useState(false);
  const [favoriteBusy, setFavoriteBusy] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [expandedDescriptionId, setExpandedDescriptionId] = useState<string | null>(null);
  const selectedJob = useMemo(() => [...jobs, ...hiddenJobs, ...favoriteJobs].find((job) => job.id === selectedId) || null, [favoriteJobs, hiddenJobs, jobs, selectedId]);

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

  useEffect(() => {
    if (mode !== "skills") return;
    const controller = new AbortController();
    setSkillsLoading(true);
    setSkillsError(null);
    fetchSkillOverview(filters, controller.signal)
      .then((result) => setSkillOverview(result))
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setSkillsError("No se pudo cargar el mapa de habilidades.");
      })
      .finally(() => setSkillsLoading(false));
    return () => controller.abort();
  }, [filters, mode]);

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
  const countValues = (read: (job: Job) => string | null) => {
    const counts = new Map<string, number>();
    for (const job of visibleJobs) {
      const value = read(job)?.trim() || "No indicado";
      counts.set(value, (counts.get(value) || 0) + 1);
    }
    return Object.fromEntries(counts);
  };
  const areaCounts = useMemo(() => countValues((job) => job.primary_area), [visibleJobs]);
  const seniorityCounts = useMemo(() => countValues((job) => ({ intern: "Practicante", junior: "Junior", mid: "Intermedio", senior: "Senior" } as Record<string, string>)[job.seniority || ""] || job.seniority), [visibleJobs]);
  const modalityCounts = useMemo(() => countValues((job) => ({ onsite: "Presencial", hybrid: "Híbrido", remote: "Remoto" } as Record<string, string>)[job.work_mode || ""] || job.work_mode), [visibleJobs]);
  const listedJobs = showHidden ? hiddenJobs : showFavorites ? favoriteJobs : visibleJobs;

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
    setExpandedDescriptionId(null);
    if (mode === "heatmap") setSelectedDistrictKey(districtKey(job.district));
  }

  function selectDistrict(key: string) {
    setSelectedDistrictKey((current) => current === key ? null : key);
    setSelectedId(null);
  }

  function clearDistrictSelection() {
    setSelectedDistrictKey(null);
    setSelectedId(null);
  }

  async function toggleHiddenJobs() {
    setStatusError(null);
    if (!showHidden && hiddenJobs.length === 0) {
      try {
        setHiddenJobs(await fetchHiddenJobs());
      } catch {
        setStatusError("No se pudieron cargar las ofertas ocultas.");
        return;
      }
    }
    setShowFavorites(false);
    setShowHidden((current) => !current);
    setSelectedId(null);
  }

  async function toggleFavoriteJobs() {
    setStatusError(null);
    if (!showFavorites && favoriteJobs.length === 0) {
      try {
        setFavoriteJobs(await fetchFavoriteJobs());
      } catch {
        setStatusError("No se pudieron cargar los favoritos.");
        return;
      }
    }
    setShowHidden(false);
    setShowFavorites((current) => !current);
    setSelectedId(null);
  }

  async function toggleFavorite(job: Job) {
    const nextValue = !job.is_favorite;
    setFavoriteBusy(true);
    setStatusError(null);
    try {
      await updateJobFavorite(job.id, nextValue);
      const update = (item: Job) => item.id === job.id ? { ...item, is_favorite: nextValue } : item;
      setJobs((current) => current.map(update));
      setHiddenJobs((current) => current.map(update));
      setFavoriteJobs((current) => nextValue
        ? [{ ...job, is_favorite: true }, ...current.filter((item) => item.id !== job.id)]
        : current.filter((item) => item.id !== job.id));
      if (!nextValue && showFavorites) setSelectedId(null);
    } catch {
      setStatusError(nextValue ? "No se pudo guardar el favorito." : "No se pudo quitar el favorito.");
    } finally {
      setFavoriteBusy(false);
    }
  }

  async function hideSelectedJob() {
    if (!selectedJob || !hideReasonFor || !hideReason) return;
    setStatusBusy(true);
    setStatusError(null);
    try {
      await updateJobStatus(selectedJob.id, "hidden", hideReason);
      setJobs((current) => current.filter((job) => job.id !== selectedJob.id));
      setHiddenJobs((current) => [{ ...selectedJob, user_status: "hidden", user_reason: hideReason }, ...current.filter((job) => job.id !== selectedJob.id)]);
      setHideReasonFor(null);
      setHideReason("");
      setSelectedId(null);
    } catch {
      setStatusError("No se pudo ocultar la oferta.");
    } finally {
      setStatusBusy(false);
    }
  }

  async function restoreJob(job: Job) {
    setStatusBusy(true);
    setStatusError(null);
    try {
      await updateJobStatus(job.id, "visible");
      setHiddenJobs((current) => current.filter((item) => item.id !== job.id));
      if (showHidden) setSelectedId(null);
      const refreshed = await fetchJobs(filters);
      setJobs(refreshed);
    } catch {
      setStatusError("No se pudo restaurar la oferta.");
    } finally {
      setStatusBusy(false);
    }
  }

  function selectRadarDistrict(key: string) {
    const district = districtStats.find((item) => item.key === key);
    if (!district) return;
    setRadarDistrictKey(key);
    setRadarCenter({ longitude: district.longitude, latitude: district.latitude });
    setRadarCenterOpen(false);
    setSelectedId(null);
  }

  function changeMode(nextMode: MapMode) {
    setMode(nextMode);
    setRadarCenterOpen(false);
    setSelectedId(null);
    if (nextMode !== "heatmap") setSelectedDistrictKey(null);
    if (nextMode === "radar") {
      setRadarDistrictKey(null);
      setRadarCenter({ longitude: -77.043, latitude: -12.046 });
    }
  }

  return (
    <main className="radar-shell">
      <section className="workspace">
        <aside className="sidebar">
          <div className="sidebar-heading"><h1>Radar</h1></div>
          <form className="search-box" onSubmit={submitSearch}><span>⌕</span><input value={draftSearch} onChange={(event) => setDraftSearch(event.target.value)} placeholder="Buscar cargo, skill o empresa" /><button type="submit" aria-label="Buscar">↵</button></form>

          <div className="filter-section"><div className="section-label">Filtros activos <span>{Object.values(filters).filter(Boolean).length}</span></div>
            <label>Área profesional<select value={filters.area} onChange={(event) => updateFilter("area", event.target.value)}>{AREAS.map((area) => <option key={area} value={area}>{area || `Todas las áreas · ${visibleJobs.length || 0}`}{area && ` · ${areaCounts[area] || 0}`}</option>)}</select></label>
            <div className="two-columns"><label>Seniority<select value={filters.seniority} onChange={(event) => updateFilter("seniority", event.target.value)}><option value="">Todos{visibleJobs.length ? ` · ${visibleJobs.length}` : ""}</option><option value="intern">Practicante · {seniorityCounts.Practicante || 0}</option><option value="junior">Junior · {seniorityCounts.Junior || 0}</option><option value="mid">Intermedio · {seniorityCounts.Intermedio || 0}</option><option value="senior">Senior · {seniorityCounts.Senior || 0}</option></select></label><label>Modalidad<select value={filters.work_mode} onChange={(event) => updateFilter("work_mode", event.target.value)}><option value="">Todas{visibleJobs.length ? ` · ${visibleJobs.length}` : ""}</option><option value="onsite">Presencial · {modalityCounts.Presencial || 0}</option><option value="hybrid">Híbrido · {modalityCounts.Híbrido || 0}</option><option value="remote">Remoto · {modalityCounts.Remoto || 0}</option></select></label></div>
            <div className="two-columns"><label>Salario mínimo<input type="number" min="0" placeholder="S/" value={filters.min_salary} onChange={(event) => updateFilter("min_salary", event.target.value)} /></label><label>Antigüedad<select value={filters.max_age_days} onChange={(event) => updateFilter("max_age_days", event.target.value)}><option value="7">7 días</option><option value="14">14 días</option><option value="30">30 días</option><option value="90">90 días</option></select></label></div>
          </div>

          <div className="map-mode"><div className="section-label">Visualización</div><div className="segmented">{([["heatmap", "Distritos"], ["radar", "Radar"], ["skills", "Competencias"]] as const).map(([value, label]) => <button key={value} className={mode === value ? "active" : ""} onClick={() => changeMode(value)} type="button">{label}</button>)}</div>{mode === "radar" && <div className="radar-controls"><div className="radar-center-control"><span>Centro del radar</span><div className="radar-center-select"><button className={radarCenterOpen ? "open" : ""} type="button" aria-haspopup="listbox" aria-expanded={radarCenterOpen} onClick={() => setRadarCenterOpen((current) => !current)}>{radarDistrict ? `${radarDistrict.district} · ${radarDistrict.count} ofertas` : "Selecciona un distrito"}<b>⌄</b></button>{radarCenterOpen && <div className="radar-center-menu" role="listbox" aria-label="Centro del radar">{districtStats.map((district) => <button key={district.key} className={radarDistrictKey === district.key ? "active" : ""} type="button" role="option" aria-selected={radarDistrictKey === district.key} onClick={() => selectRadarDistrict(district.key)}>{district.district}<span>{district.count} ofertas</span></button>)}</div>}</div></div><span className="radar-readout">CENTER // {radarDistrict?.district || "LIMA"} · RANGE // {radarRadiusKm} KM · {visibleJobs.length} MATCHES</span><div className="radar-radius">{radarRadiusCounts.map(({ radius, count }) => <button key={radius} className={radarRadiusKm === radius ? "active" : ""} type="button" onClick={() => { setRadarRadiusKm(radius); setSelectedId(null); }}><strong>{radius} KM</strong><span>{count} ofertas</span></button>)}</div></div>}</div>
          <div className="job-list-header"><span>{showHidden ? "Ofertas ocultas" : showFavorites ? "Favoritos" : selectedDistrict ? `Ofertas en ${selectedDistrict.district}` : "Ofertas recientes"}</span><div className="job-list-tools"><span>{loading && !showHidden && !showFavorites ? "…" : `${showHidden ? hiddenJobs.length : showFavorites ? favoriteJobs.length : visibleJobs.filter((job) => job.latitude !== null && job.longitude !== null).length} ${showHidden ? "ocultas" : showFavorites ? "guardadas" : "en mapa"}`}</span><button className={`favorites-toggle ${showFavorites ? "active" : ""}`} type="button" onClick={toggleFavoriteJobs} aria-label={showFavorites ? "Volver a ofertas visibles" : "Ver favoritos"} title={showFavorites ? "Volver a ofertas visibles" : "Ver favoritos"}>{favoriteJobs.length > 0 ? "★" : "☆"}</button><button className={`hidden-toggle ${showHidden ? "active" : ""}`} type="button" onClick={toggleHiddenJobs} aria-label={showHidden ? "Volver a ofertas visibles" : "Ver ofertas ocultas"} title={showHidden ? "Volver a ofertas visibles" : "Ver ofertas ocultas"}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.5" /></svg>{hiddenJobs.length > 0 && <b>{hiddenJobs.length}</b>}</button></div></div>
          {statusError && <div className="status-error">{statusError}</div>}
          <div className="job-list">{loading && !showHidden && !showFavorites && <div className="empty-state">Buscando ofertas…</div>}{!loading && error && !showHidden && !showFavorites && <div className="empty-state error-state">{error}</div>}{!loading && !error && listedJobs.length === 0 && <div className="empty-state">{showHidden ? "No tienes ofertas ocultas." : showFavorites ? "No tienes favoritos guardados." : "No hay ofertas con estos filtros."}</div>}{listedJobs.map((job) => <button key={job.id} className={`job-card ${selectedId === job.id ? "selected" : ""}`} onClick={() => selectJob(job)}><div className="job-card-top"><span className="job-area">{job.primary_area || "Sin área"}</span><span className="job-date">{formatDate(job.published_at)}</span><span className="favorite-toggle" role="button" tabIndex={0} aria-label={job.is_favorite ? "Quitar de favoritos" : "Añadir a favoritos"} title={job.is_favorite ? "Quitar de favoritos" : "Añadir a favoritos"} onClick={(event) => { event.stopPropagation(); void toggleFavorite(job); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); void toggleFavorite(job); } }}>{job.is_favorite ? "★" : "☆"}</span></div><strong>{job.title}</strong><span className="job-company">{job.company || "Empresa no indicada"}</span><div className="job-meta"><span>⌖ {job.district || job.location || "Ubicación pendiente"}</span><span>{job.work_mode === "hybrid" ? "Híbrido" : job.work_mode === "remote" ? "Remoto" : job.work_mode === "onsite" ? "Presencial" : "Modalidad n/i"}</span></div>{showHidden && <span className="hidden-reason">{job.user_reason || "Oculta"} · Restaurar desde el detalle</span>}</button>)}</div>
        </aside>

        <section className={`map-panel ${mode === "skills" ? "skills-panel" : ""}`}>
          {mode === "skills" ? <SkillsView data={skillOverview} loading={skillsLoading} error={skillsError} /> : <>
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
            {mode === "heatmap" && districtStats.length > 0 && <aside className="district-map-overlay"><div className="district-overlay-heading"><div><p className="eyebrow">{selectedDistrict ? "Distrito seleccionado" : "Distritos con más oportunidades"}</p><strong>{selectedDistrict?.district || "Todos los distritos"}</strong><span>{selectedDistrict ? `${selectedDistrict.count} ofertas con estos filtros` : "Selecciona un distrito para filtrar el mapa"}</span></div>{selectedDistrict && <button className="overlay-action" type="button" onClick={clearDistrictSelection}>Ver todos</button>}</div><div className="district-overlay-list">{(showAllDistricts ? districtStats : districtStats.slice(0, 6)).map((district) => <button key={district.key} className={`district-row ${selectedDistrictKey === district.key ? "selected" : ""}`} onClick={() => selectDistrict(district.key)} type="button"><span className="district-row-top"><strong>{district.district}</strong><span>{district.count}</span></span><span className="district-bar"><i style={{ width: `${Math.max(10, (district.count / districtStats[0].count) * 100)}%` }} /></span></button>)}</div><button className="overlay-more" type="button" onClick={() => setShowAllDistricts((current) => !current)}>{showAllDistricts ? "Ver principales" : `Ver otros distritos (${Math.max(0, districtStats.length - 6)})`}</button></aside>}
            {selectedJob && <article className={`job-popover ${expandedDescriptionId === selectedJob.id ? "is-description-expanded" : ""}`}><button className="close-button" onClick={() => { setSelectedId(null); setExpandedDescriptionId(null); }} aria-label="Cerrar detalle" type="button">×</button><span className="job-area">{selectedJob.primary_area || "Sin área"}</span><h3>{selectedJob.title}</h3><p className="popover-company">{selectedJob.company || "Empresa no indicada"}</p><div className="popover-divider" /><div className="popover-grid"><div><span>Ubicación</span><strong>{selectedJob.district || selectedJob.location || "Pendiente"}</strong></div><div><span>Modalidad</span><strong>{selectedJob.work_mode === "hybrid" ? "Híbrido" : selectedJob.work_mode === "remote" ? "Remoto" : selectedJob.work_mode === "onsite" ? "Presencial" : "No indicada"}</strong></div><div><span>Salario</span><strong>{formatSalary(selectedJob)}</strong></div><div><span>Publicado</span><strong>{formatDate(selectedJob.published_at)}</strong></div></div>{selectedJob.description && <div className="popover-description-wrap"><button className="description-toggle" type="button" aria-label="Ver descripción completa" title="Ver descripción completa" aria-expanded={expandedDescriptionId === selectedJob.id} onClick={() => setExpandedDescriptionId((current) => current === selectedJob.id ? null : selectedJob.id)}><span className="popover-description">{selectedJob.description}</span></button></div>}<div className={`popover-actions ${hideReasonFor === selectedJob.id ? "is-hiding" : ""}`}>{selectedJob.url && <a className="popover-link" href={selectedJob.url} target="_blank" rel="noreferrer">{sourceLabel(selectedJob.url)} ↗</a>}{selectedJob.user_status === "hidden" ? <button className="restore-button" type="button" disabled={statusBusy} onClick={() => restoreJob(selectedJob)}>{statusBusy ? "Restaurando…" : "Restaurar oferta"}</button> : <div className="hide-controls">{hideReasonFor === selectedJob.id ? <><label>Motivo de ocultar<select value={hideReason} onChange={(event) => setHideReason(event.target.value)}><option value="" disabled>Selecciona un motivo</option><option value="closed">Ya cerró</option><option value="not_interested">No me interesa</option><option value="applied">Ya postulé</option><option value="duplicate">Oferta duplicada</option><option value="other">Otro</option></select></label><button className="restore-button" type="button" disabled={statusBusy || !hideReason} onClick={() => hideSelectedJob()}>{statusBusy ? "Guardando…" : "Confirmar ocultar"}</button><button className="cancel-hide" type="button" onClick={() => { setHideReasonFor(null); setHideReason(""); }}>Cancelar</button></> : <button className="hide-button" type="button" aria-label="Ocultar oferta" title="Ocultar oferta" onClick={() => { setHideReasonFor(selectedJob.id); setHideReason(""); }}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.5" /></svg><span>Ocultar</span></button>}</div>}</div></article>}
          </div>
          </>}
        </section>

      </section>
      <footer className="statusbar"><span><i className="status-dot" /> API Radar conectada</span><span>Fuente de verdad: PostgreSQL</span><span>Actualización: últimas {filters.max_age_days} días</span></footer>
    </main>
  );
}
