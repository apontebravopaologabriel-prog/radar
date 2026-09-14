"use client";

import dynamic from "next/dynamic";
import { FormEvent, PointerEvent as ReactPointerEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { fetchFavoriteJobs, fetchHiddenJobs, fetchJobs, fetchSkillHistory, fetchSkillOverview, updateJobFavorite, updateJobStatus } from "../lib/api";
import { districtKey } from "../lib/districts";
import type { DistrictSummary, Filters, Job, MapMode, SkillOverview, SkillSnapshot } from "../types";
import SkillsView from "./SkillsView";

const MapView = dynamic(() => import("./MapView"), { ssr: false, loading: () => <div className="map-loading">Cargando mapa de Lima…</div> });

const AREAS = ["", "Operaciones", "Producción", "Mejora continua", "Procesos", "Supply Chain", "Logística", "Compras", "Planeamiento", "Demand Planning", "Calidad", "Data / BI", "Analytics", "Automatización", "Proyectos / PMO", "Finanzas / Control de gestión", "Seguridad y Salud en el Trabajo", "Recursos Humanos / People Analytics"];
const INITIAL_FILTERS: Filters = { search: "", area: "", seniority: "", work_mode: "", min_salary: "", max_age_days: "7" };
const RADAR_RADII = [2, 5, 10] as const;
type RadarTool = "districts" | "radar" | "filters";

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

const INLINE_MARKDOWN = /(\*\*(.+?)\*\*|__(.+?)__|\*(.+?)\*|_(.+?)_|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))/g;

function renderInlineMarkdown(value: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let key = 0;
  for (const match of value.matchAll(INLINE_MARKDOWN)) {
    const token = match[0];
    const index = match.index ?? cursor;
    if (index > cursor) nodes.push(value.slice(cursor, index));
    if (match[2] || match[3]) nodes.push(<strong key={`strong-${key++}`}>{match[2] || match[3]}</strong>);
    else if (match[4] || match[5]) nodes.push(<em key={`em-${key++}`}>{match[4] || match[5]}</em>);
    else if (match[6]) nodes.push(<code key={`code-${key++}`}>{match[6]}</code>);
    else if (match[7] && match[8]) nodes.push(<a key={`link-${key++}`} href={match[8]} target="_blank" rel="noreferrer">{match[7]}</a>);
    else nodes.push(token);
    cursor = index + token.length;
  }
  if (cursor < value.length) nodes.push(value.slice(cursor));
  return nodes;
}

function renderMarkdown(value: string): ReactNode[] {
  const blocks: ReactNode[] = [];
  const lines = value.replace(/\r\n?/g, "\n").split("\n");
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let listOrdered: boolean | null = null;
  let key = 0;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(<p key={`paragraph-${key++}`}>{renderInlineMarkdown(paragraph.join(" "))}</p>);
    paragraph = [];
  };
  const flushList = () => {
    if (!listItems.length || listOrdered === null) return;
    const ListTag = listOrdered ? "ol" : "ul";
    blocks.push(<ListTag key={`list-${key++}`}>{listItems.map((item, index) => <li key={`item-${index}`}>{renderInlineMarkdown(item)}</li>)}</ListTag>);
    listItems = [];
    listOrdered = null;
  };

  for (const line of lines) {
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push(<h4 key={`heading-${key++}`}>{renderInlineMarkdown(heading[1])}</h4>);
      continue;
    }
    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const isOrdered = Boolean(ordered);
      if (listOrdered !== null && listOrdered !== isOrdered) flushList();
      listOrdered = isOrdered;
      listItems.push((ordered || unordered)?.[1] || "");
      continue;
    }
    flushList();
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  return blocks;
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
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
  const [mode, setMode] = useState<MapMode>("heatmap");
  const [selectedDistrictKey, setSelectedDistrictKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [skillOverview, setSkillOverview] = useState<SkillOverview | null>(null);
  const [skillHistory, setSkillHistory] = useState<SkillSnapshot[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState<string | null>(null);
  const [radarCenter, setRadarCenter] = useState({ longitude: -77.043, latitude: -12.046 });
  const [radarRadiusKm, setRadarRadiusKm] = useState<number>(5);
  const [radarDistrictKey, setRadarDistrictKey] = useState<string | null>(null);
  const [radarCenterOpen, setRadarCenterOpen] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [showFavorites, setShowFavorites] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [activeTool, setActiveTool] = useState<RadarTool>("districts");
  const [hideReasonFor, setHideReasonFor] = useState<string | null>(null);
  const [hideReason, setHideReason] = useState("");
  const [statusBusy, setStatusBusy] = useState(false);
  const [favoriteBusy, setFavoriteBusy] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [offerPanelHeight, setOfferPanelHeight] = useState<number | null>(null);
  const offerResizeRef = useRef<{ startY: number; startHeight: number } | null>(null);
  const [expandedDescriptionId, setExpandedDescriptionId] = useState<string | null>(null);
  const selectedJob = useMemo(() => [...jobs, ...hiddenJobs, ...favoriteJobs].find((job) => job.id === selectedId) || null, [favoriteJobs, hiddenJobs, jobs, selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchJobs(selectedSkill ? { ...filters, skill: selectedSkill } : filters, controller.signal)
      .then((result) => setJobs(result))
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError("No se pudo conectar con Radar API. Inicia `radar-api` y vuelve a cargar.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [filters, selectedSkill]);

  useEffect(() => {
    if (mode !== "skills") return;
    const controller = new AbortController();
    setSkillsLoading(true);
    setSkillsError(null);
    Promise.all([fetchSkillOverview(filters, controller.signal), fetchSkillHistory(controller.signal)])
      .then(([result, snapshots]) => { setSkillOverview(result); setSkillHistory(snapshots); })
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
    if (nextMode !== "skills") setSelectedSkill(null);
    if (nextMode !== "heatmap") setSelectedDistrictKey(null);
    if (nextMode === "radar") {
      setRadarDistrictKey(null);
      setRadarCenter({ longitude: -77.043, latitude: -12.046 });
    }
  }

  function selectTool(tool: RadarTool) {
    setActiveTool(tool);
    setRadarCenterOpen(false);
    if (tool === "districts") {
      setFiltersOpen(false);
      changeMode("heatmap");
      return;
    }
    setFiltersOpen(true);
    changeMode(tool === "radar" ? "radar" : "heatmap");
  }

  useEffect(() => {
    function resizeOffers(event: PointerEvent) {
      const resize = offerResizeRef.current;
      if (!resize) return;
      const maxHeight = Math.max(180, window.innerHeight - 36);
      setOfferPanelHeight(Math.max(180, Math.min(maxHeight, resize.startHeight + resize.startY - event.clientY)));
    }
    function stopResizingOffers() {
      offerResizeRef.current = null;
    }
    window.addEventListener("pointermove", resizeOffers);
    window.addEventListener("pointerup", stopResizingOffers);
    return () => {
      window.removeEventListener("pointermove", resizeOffers);
      window.removeEventListener("pointerup", stopResizingOffers);
    };
  }, []);

  function startOfferResize(event: ReactPointerEvent<HTMLDivElement>) {
    const panel = event.currentTarget.parentElement;
    if (!panel) return;
    event.preventDefault();
    offerResizeRef.current = { startY: event.clientY, startHeight: panel.getBoundingClientRect().height };
  }

  return (
    <main className="radar-shell">
      <section className="workspace">
        <button className={`edge-menu-toggle ${filtersOpen ? "is-open" : ""}`} type="button" aria-expanded={filtersOpen} aria-controls="radar-controls-panel" onClick={() => filtersOpen ? setFiltersOpen(false) : selectTool("filters")}>
          <span aria-hidden="true">{filtersOpen ? "×" : "☷"}</span>
          <small>{filtersOpen ? "Cerrar" : "Menu"}</small>
        </button>
        <nav className="mode-rail" aria-label="Herramientas del mapa">
          <button className={activeTool === "filters" ? "active" : ""} type="button" aria-label="Filtros" title="Filtros" onClick={() => selectTool("filters")}><span aria-hidden="true">≡</span></button>
          <button className={activeTool === "radar" ? "active" : ""} type="button" aria-label="Radar" title="Radar" onClick={() => selectTool("radar")}><span aria-hidden="true">◎</span></button>
        </nav>
        <aside id="radar-controls-panel" className={`sidebar tool-${activeTool} ${filtersOpen ? "is-open" : ""}`}>
          <div className="sidebar-heading">
            <div><p className="eyebrow">Control room / 01</p><h1>Market scan</h1></div>
            <span className="result-count">{loading ? "---" : `${mappedCount}`}</span>
          </div>
          <form className="search-box" onSubmit={submitSearch}><span>⌕</span><input value={draftSearch} onChange={(event) => setDraftSearch(event.target.value)} placeholder="..." /><button type="submit" aria-label="Buscar">↵</button></form>

          <div className="filter-section"><div className="section-label">Filtros activos <span>{Object.values(filters).filter(Boolean).length}</span></div>
            <label>Área profesional<select value={filters.area} onChange={(event) => updateFilter("area", event.target.value)}>{AREAS.map((area) => <option key={area} value={area}>{area || `Todas las áreas · ${visibleJobs.length || 0}`}{area && ` · ${areaCounts[area] || 0}`}</option>)}</select></label>
            <div className="two-columns"><label>Seniority<select value={filters.seniority} onChange={(event) => updateFilter("seniority", event.target.value)}><option value="">Todos{visibleJobs.length ? ` · ${visibleJobs.length}` : ""}</option><option value="intern">Practicante · {seniorityCounts.Practicante || 0}</option><option value="junior">Junior · {seniorityCounts.Junior || 0}</option><option value="mid">Intermedio · {seniorityCounts.Intermedio || 0}</option><option value="senior">Senior · {seniorityCounts.Senior || 0}</option></select></label><label>Modalidad<select value={filters.work_mode} onChange={(event) => updateFilter("work_mode", event.target.value)}><option value="">Todas{visibleJobs.length ? ` · ${visibleJobs.length}` : ""}</option><option value="onsite">Presencial · {modalityCounts.Presencial || 0}</option><option value="hybrid">Híbrido · {modalityCounts.Híbrido || 0}</option><option value="remote">Remoto · {modalityCounts.Remoto || 0}</option></select></label></div>
            <div className="two-columns"><label>Salario mínimo<input type="number" min="0" placeholder="S/" value={filters.min_salary} onChange={(event) => updateFilter("min_salary", event.target.value)} /></label><label>Antigüedad<select value={filters.max_age_days} onChange={(event) => updateFilter("max_age_days", event.target.value)}><option value="7">7 días</option><option value="14">14 días</option><option value="30">30 días</option><option value="90">90 días</option></select></label></div>
          </div>

          <div className="map-mode"><div className="section-label">Visualización</div><div className="segmented">{([["jobs", "Ofertas"], ["heatmap", "Distritos"], ["radar", "Radar"], ["skills", "Competencias"]] as const).map(([value, label]) => <button key={value} className={mode === value ? "active" : ""} onClick={() => changeMode(value)} type="button">{label}</button>)}</div>{mode === "radar" && <div className="radar-controls"><div className="radar-center-control"><span>Centro del radar</span><div className="radar-center-select"><button className={radarCenterOpen ? "open" : ""} type="button" aria-haspopup="listbox" aria-expanded={radarCenterOpen} onClick={() => setRadarCenterOpen((current) => !current)}>{radarDistrict ? `${radarDistrict.district} · ${radarDistrict.count} ofertas` : "Selecciona un distrito"}<b>⌄</b></button>{radarCenterOpen && <div className="radar-center-menu" role="listbox" aria-label="Centro del radar">{districtStats.map((district) => <button key={district.key} className={radarDistrictKey === district.key ? "active" : ""} type="button" role="option" aria-selected={radarDistrictKey === district.key} onClick={() => selectRadarDistrict(district.key)}>{district.district}<span>{district.count} ofertas</span></button>)}</div>}</div></div><span className="radar-readout">CENTER // {radarDistrict?.district || "LIMA"} · RANGE // {radarRadiusKm} KM · {visibleJobs.length} MATCHES</span><div className="radar-radius">{radarRadiusCounts.map(({ radius, count }) => <button key={radius} className={radarRadiusKm === radius ? "active" : ""} type="button" onClick={() => { setRadarRadiusKm(radius); setSelectedId(null); }}><strong>{radius} KM</strong><span>{count} ofertas</span></button>)}</div></div>}</div>
          <div className="job-list-header"><span>{showHidden ? "Ofertas ocultas" : showFavorites ? "Favoritos" : selectedSkill ? `Ofertas con ${selectedSkill}` : selectedDistrict ? `Ofertas en ${selectedDistrict.district}` : "Ofertas recientes"}</span><div className="job-list-tools"><span>{loading && !showHidden && !showFavorites ? "…" : `${showHidden ? hiddenJobs.length : showFavorites ? favoriteJobs.length : visibleJobs.filter((job) => job.latitude !== null && job.longitude !== null).length} ${showHidden ? "ocultas" : showFavorites ? "guardadas" : "en mapa"}`}</span>{selectedSkill && !showHidden && !showFavorites && <button className="clear-skill-filter" type="button" onClick={() => setSelectedSkill(null)} aria-label="Quitar filtro de competencia" title="Quitar filtro de competencia">×</button>}<button className={`favorites-toggle ${showFavorites ? "active" : ""}`} type="button" onClick={toggleFavoriteJobs} aria-label={showFavorites ? "Volver a ofertas visibles" : "Ver favoritos"} title={showFavorites ? "Volver a ofertas visibles" : "Ver favoritos"}>{favoriteJobs.length > 0 ? "★" : "☆"}</button><button className={`hidden-toggle ${showHidden ? "active" : ""}`} type="button" onClick={toggleHiddenJobs} aria-label={showHidden ? "Volver a ofertas visibles" : "Ver ofertas ocultas"} title={showHidden ? "Volver a ofertas visibles" : "Ver ofertas ocultas"}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.5" /></svg>{hiddenJobs.length > 0 && <b>{hiddenJobs.length}</b>}</button></div></div>
          {statusError && <div className="status-error">{statusError}</div>}
          <div className="job-list">{loading && !showHidden && !showFavorites && <div className="empty-state">Buscando ofertas…</div>}{!loading && error && !showHidden && !showFavorites && <div className="empty-state error-state">{error}</div>}{!loading && !error && listedJobs.length === 0 && <div className="empty-state">{showHidden ? "No tienes ofertas ocultas." : showFavorites ? "No tienes favoritos guardados." : "No hay ofertas con estos filtros."}</div>}{listedJobs.map((job) => <button key={job.id} className={`job-card ${selectedId === job.id ? "selected" : ""}`} onClick={() => selectJob(job)}><div className="job-card-top"><span className="job-area">{job.primary_area || "Sin área"}</span><span className="job-date">{formatDate(job.published_at)}</span><span className="favorite-toggle" role="button" tabIndex={0} aria-label={job.is_favorite ? "Quitar de favoritos" : "Añadir a favoritos"} title={job.is_favorite ? "Quitar de favoritos" : "Añadir a favoritos"} onClick={(event) => { event.stopPropagation(); void toggleFavorite(job); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); void toggleFavorite(job); } }}>{job.is_favorite ? "★" : "☆"}</span></div><strong>{job.title}</strong><span className="job-company">{job.company || "Empresa no indicada"}</span><div className="job-meta"><span>⌖ {job.district || job.location || "Ubicación pendiente"}</span><span>{job.work_mode === "hybrid" ? "Híbrido" : job.work_mode === "remote" ? "Remoto" : job.work_mode === "onsite" ? "Presencial" : "Modalidad n/i"}</span></div>{showHidden && <span className="hidden-reason">{job.user_reason || "Oculta"} · Restaurar desde el detalle</span>}</button>)}</div>
        </aside>

        <section className={`map-panel ${mode === "skills" ? "skills-panel" : mode === "jobs" ? "reading-panel" : ""}`}>
          {mode === "jobs" ? (
            <div className="job-reading-view">
              {selectedJob ? (
                <article className="reading-card">
                  <header className="reading-header">
                    <div className="reading-header-top">
                      <span className="reading-badge area">{selectedJob.primary_area || "General"}</span>
                      <span className="reading-badge date">{formatDate(selectedJob.published_at)}</span>
                      <button type="button" className={`reading-fav-btn ${selectedJob.is_favorite ? "active" : ""}`} onClick={() => void toggleFavorite(selectedJob)}>
                        {selectedJob.is_favorite ? "★ Guardado" : "☆ Guardar"}
                      </button>
                    </div>
                    <h2 className="reading-title">{selectedJob.title}</h2>
                    <p className="reading-company">{selectedJob.company || "Empresa no indicada"}</p>
                  </header>

                  <div className="reading-meta-grid">
                    <div className="meta-box"><span className="meta-label">Ubicación</span><strong className="meta-val">{selectedJob.district || selectedJob.location || "Lima, Perú"}</strong></div>
                    <div className="meta-box"><span className="meta-label">Modalidad</span><strong className="meta-val">{selectedJob.work_mode === "hybrid" ? "Híbrido" : selectedJob.work_mode === "remote" ? "Remoto" : selectedJob.work_mode === "onsite" ? "Presencial" : "No indicada"}</strong></div>
                    <div className="meta-box"><span className="meta-label">Salario</span><strong className="meta-val">{formatSalary(selectedJob)}</strong></div>
                    <div className="meta-box"><span className="meta-label">Jornada</span><strong className="meta-val">{selectedJob.hours_per_week ? `${selectedJob.hours_per_week}h/sem` : selectedJob.schedule_text || "Completa"}</strong></div>
                  </div>

                  <div className="reading-actions">
                    {selectedJob.url && <a className="reading-apply-btn" href={selectedJob.url} target="_blank" rel="noreferrer">{sourceLabel(selectedJob.url)} ↗</a>}
                    {selectedJob.user_status === "hidden" ? (
                      <button className="restore-button" type="button" disabled={statusBusy} onClick={() => restoreJob(selectedJob)}>{statusBusy ? "Restaurando…" : "Restaurar oferta"}</button>
                    ) : hideReasonFor === selectedJob.id ? (
                      <div className="reading-hide-form">
                        <select value={hideReason} onChange={(e) => setHideReason(e.target.value)}>
                          <option value="" disabled>Selecciona un motivo</option>
                          <option value="closed">Ya cerró</option>
                          <option value="not_interested">No me interesa</option>
                          <option value="applied">Ya postulé</option>
                          <option value="duplicate">Oferta duplicada</option>
                          <option value="other">Otro</option>
                        </select>
                        <button className="restore-button" type="button" disabled={statusBusy || !hideReason} onClick={() => hideSelectedJob()}>{statusBusy ? "Guardando…" : "Confirmar"}</button>
                        <button className="cancel-hide" type="button" onClick={() => { setHideReasonFor(null); setHideReason(""); }}>Cancelar</button>
                      </div>
                    ) : (
                      <button className="reading-hide-trigger" type="button" onClick={() => { setHideReasonFor(selectedJob.id); setHideReason(""); }}>Ocultar oferta</button>
                    )}
                  </div>

                  <div className="reading-body">
                    <h3>Descripción y Requisitos</h3>
                    <div className="reading-description">
                      {selectedJob.description ? renderMarkdown(selectedJob.description) : <p>Sin descripción disponible para esta oferta.</p>}
                    </div>
                  </div>
                </article>
              ) : (
                <div className="reading-empty">
                  <div className="empty-icon">📋</div>
                  <h3>Selecciona una oferta</h3>
                  <p>Haz clic en cualquier oferta de la lista para leer su descripción detallada, requisitos y enlace de postulación.</p>
                </div>
              )}
            </div>
          ) : mode === "skills" ? (
            <SkillsView data={skillOverview} history={skillHistory} loading={skillsLoading} error={skillsError} selectedName={selectedSkill} onSelectSkill={setSelectedSkill} />
          ) : (
            <>
              <div className="map-header">
                <div>
                  <p className="eyebrow">Geospatial intelligence / Lima</p>
                  <h2>{mode === "heatmap" && selectedDistrict ? selectedDistrict.district : mode === "heatmap" ? "Data analysis" : mode === "radar" ? `Signal lock${radarDistrict ? ` · ${radarDistrict.district}` : ""}` : "Lima Metropolitana"}</h2>
                </div>
                <div className="map-legend">
                  {mode === "heatmap" ? <><span><i className="legend-scale low" /> Pocas ofertas</span><span><i className="legend-scale high" /> Más ofertas</span></> : <><span><i className="legend-dot" /> Oferta cercana</span><span><i className="legend-cluster" /> Concentración</span></>}
                  {mode === "radar" && <span><i className="legend-ring" /> Radio activo</span>}
                </div>
              </div>
              <div className={`map-wrap ${mode === "radar" ? "radar-active" : ""}`}>
                <MapView jobs={visibleJobs} mode={mode} radarCenter={radarCenter} radarRadiusKm={radarRadiusKm} radarDistrictKey={radarDistrictKey} selectedDistrictKey={selectedDistrictKey} onSelectJob={(jobId) => { const job = visibleJobs.find((item) => item.id === jobId); if (job) selectJob(job); }} onSelectDistrict={selectDistrict} />
                {(mode === "heatmap" || mode === "radar") && <aside className="offer-scroll" aria-label="Ofertas visibles" style={offerPanelHeight ? { height: `${offerPanelHeight}px` } : undefined}><div className="offer-resize-handle" role="separator" aria-label="Ajustar altura de ofertas" onPointerDown={startOfferResize} /><div className="offer-scroll-heading"><span>SEÑALES // OFERTAS</span><strong>{visibleJobs.length.toString().padStart(3, "0")}</strong></div><div className="offer-scroll-list">{visibleJobs.map((job) => <button key={job.id} className={`offer-scroll-card ${selectedId === job.id ? "selected" : ""}`} type="button" onClick={() => selectJob(job)}><span className="offer-scroll-meta"><span>{job.primary_area || "Sin área"}</span><span>{formatDate(job.published_at)}</span></span><strong>{job.title}</strong><span className="offer-scroll-company">{job.company || "Empresa no indicada"}</span><span className="offer-scroll-location">⌖ {job.district || job.location || "Ubicación pendiente"}</span></button>)}{!loading && visibleJobs.length === 0 && <span className="offer-scroll-empty">Selecciona un distrito para cargar señales</span>}</div></aside>}
                <div className="map-scan-label map-scan-label-top"><span className="scan-live-dot" />{mode === "radar" ? "RADAR LOCK" : mode === "heatmap" ? "DATA ANALYSIS" : "COLLECTING DATA"}<small>/// LIMA METROPOLITANA</small></div>
                <div className="map-scan-label map-scan-label-bottom"><span>COORD // 12°02'46.0&quot;S 77°02'35.0&quot;W</span><span>TRACKING // {visibleJobs.length.toString().padStart(3, "0")} SIGNALS</span></div>
                {mode === "heatmap" && districtStats.length > 0 && <aside className="district-map-overlay" aria-label="Distritos con ofertas"><div className="district-overlay-list"><button className={`district-row district-row-all ${selectedDistrictKey === null ? "selected" : ""}`} onClick={() => { setSelectedDistrictKey(null); setSelectedId(null); }} type="button"><span className="district-row-top"><strong>Todos</strong><span>{mappedCount}</span></span><span className="district-bar"><i style={{ width: "100%" }} /></span></button>{districtStats.map((district) => <button key={district.key} className={`district-row ${selectedDistrictKey === district.key ? "selected" : ""}`} onClick={() => selectDistrict(district.key)} type="button"><span className="district-row-top"><strong>{district.district}</strong><span>{district.count}</span></span><span className="district-bar"><i style={{ width: `${Math.max(10, (district.count / districtStats[0].count) * 100)}%` }} /></span></button>)}</div></aside>}
                {selectedJob && <article className={`job-popover ${expandedDescriptionId === selectedJob.id ? "is-description-expanded" : ""}`}>
                  <button className="close-button" onClick={() => { setSelectedId(null); setExpandedDescriptionId(null); }} aria-label="Cerrar detalle" type="button">×</button>
                  <span className="job-area">{selectedJob.primary_area || "Sin área"}</span>
                  <h3>{selectedJob.title}</h3>
                  <p className="popover-company">{selectedJob.company || "Empresa no indicada"}</p>
                  <div className="popover-divider" />
                  <div className="popover-grid">
                    <div><span>Ubicación</span><strong>{selectedJob.district || selectedJob.location || "Pendiente"}</strong></div>
                    <div><span>Modalidad</span><strong>{selectedJob.work_mode === "hybrid" ? "Híbrido" : selectedJob.work_mode === "remote" ? "Remoto" : selectedJob.work_mode === "onsite" ? "Presencial" : "No indicada"}</strong></div>
                    <div><span>Salario</span><strong>{formatSalary(selectedJob)}</strong></div>
                    <div><span>Publicado</span><strong>{formatDate(selectedJob.published_at)}</strong></div>
                  </div>
                  {selectedJob.description && <div className="popover-description-wrap"><div className="description-toggle" role="button" tabIndex={0} aria-label="Ver descripción completa" title="Ver descripción completa" aria-expanded={expandedDescriptionId === selectedJob.id} onClick={() => setExpandedDescriptionId((current) => current === selectedJob.id ? null : selectedJob.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setExpandedDescriptionId((current) => current === selectedJob.id ? null : selectedJob.id); } }}><div className="popover-description">{renderMarkdown(selectedJob.description)}</div></div></div>}
                  <div className={`popover-actions ${hideReasonFor === selectedJob.id ? "is-hiding" : ""}`}>
                    {selectedJob.url && <a className="popover-link" href={selectedJob.url} target="_blank" rel="noreferrer">{sourceLabel(selectedJob.url)} ↗</a>}
                    {selectedJob.user_status === "hidden" ? <button className="restore-button" type="button" disabled={statusBusy} onClick={() => restoreJob(selectedJob)}>{statusBusy ? "Restaurando…" : "Restaurar oferta"}</button> : <div className="hide-controls">{hideReasonFor === selectedJob.id ? <><label>Motivo de ocultar<select value={hideReason} onChange={(event) => setHideReason(event.target.value)}><option value="" disabled>Selecciona un motivo</option><option value="closed">Ya cerró</option><option value="not_interested">No me interesa</option><option value="applied">Ya postulé</option><option value="duplicate">Oferta duplicada</option><option value="other">Otro</option></select></label><button className="restore-button" type="button" disabled={statusBusy || !hideReason} onClick={() => hideSelectedJob()}>{statusBusy ? "Guardando…" : "Confirmar ocultar"}</button><button className="cancel-hide" type="button" onClick={() => { setHideReasonFor(null); setHideReason(""); }}>Cancelar</button></> : <button className="hide-button" type="button" aria-label="Ocultar oferta" title="Ocultar oferta" onClick={() => { setHideReasonFor(selectedJob.id); setHideReason(""); }}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.5" /></svg><span>Ocultar</span></button>}</div>}
                  </div>
                </article>}
              </div>
            </>
          )}
        </section>

      </section>
    </main>
  );
}
