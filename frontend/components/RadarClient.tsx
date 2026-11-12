"use client";

import dynamic from "next/dynamic";
import { FormEvent, PointerEvent as ReactPointerEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchFavoriteJobs, fetchHiddenJobs, fetchJob, fetchJobDescription, fetchJobs, fetchSkillOverview, updateJobFavorite, updateJobStatus } from "../lib/api";
import type { AnalysisScope } from "../lib/analysis-api";
import { analysisScope, filtersFromScope } from "../lib/analysis-scope";
import { updateApplication } from "../lib/applications-api";
import { districtKey } from "../lib/districts";
import { MY_CV_EVENT, PREPARE_CV_EVENT } from "../lib/cv-events";
import { fetchMarkets, type Market } from "../lib/markets-api";
import type { AgentContext } from "../lib/mobile-api";
import {
  distanceKm,
  INITIAL_FILTERS,
  RADAR_RADII,
  type RadarView,
} from "../lib/radar-format";
import type { DistrictSummary, Filters, Job, MapMode, SkillOverview } from "../types";
import { OPEN_JOB_EVENT } from "./agent/Markdown";
import ApplicationsView from "./ProcessesView";
import MarketControls from "./MarketControls";
import { IconEyeOff, JobCard, LoadingDots, OfferSignalCard, ViewIcon } from "./radar/JobCards";
import { JobReadingView, MapJobPopover } from "./radar/JobDetailViews";
import { useProgressiveList } from "./useProgressiveList";
import "./radar-map.css";

const MapView = dynamic(() => import("./MapView"), { ssr: false, loading: () => <div className="map-loading">Cargando mapa de Lima<LoadingDots /></div> });
const AnalysisView = dynamic(() => import("./AnalysisView"), { loading: () => <div className="map-loading">Cargando análisis…</div> });
const CvView = dynamic(() => import("./CvView"), { loading: () => <div className="map-loading">Cargando Mi CV…</div> });
const SCOPE_LABELS: Record<string, string> = {
  intern: "Intern", junior: "Junior", mid: "Semi-Senior", senior: "Senior",
  onsite: "Presencial", hybrid: "Híbrido", remote: "Remoto",
  linkedin: "Linkedin", indeed: "Indeed", computrabajo: "Computrabajo", bumeran: "Bumeran", empleos: "Empleos Perú", google: "Google Jobs", laborum: "Laborum",
  English: "Inglés",
  target: "Puestos priorizados", core: "Núcleo del mercado", adjacent: "Áreas relacionadas", out_of_focus: "Fuera de foco",
};
const APPLIED_STATES = ["applied", "responded", "interview", "offer", "rejected", "ignored"];

async function fetchInterestJobs() {
  return (await fetchFavoriteJobs()).filter((job) => !APPLIED_STATES.includes(job.user_application || ""));
}

export default function RadarClient({ onAgentContextChange }: { onAgentContextChange?: (context: AgentContext) => void }) {
  const [filters, setFilters] = useState<Filters>(INITIAL_FILTERS);
  const currentFiltersRef = useRef(filters);
  currentFiltersRef.current = filters;
  const [markets, setMarkets] = useState<Market[]>([]);
  const [marketReady, setMarketReady] = useState(false);
  const marketId = filters.market_id || "industrial_engineering";
  const currentMarket = markets.find((market) => market.id === marketId);
  const areas = ["", ...new Set([...(currentMarket?.areas.core || []), ...(currentMarket?.areas.adjacent || [])])];
  const [marketRevision, setMarketRevision] = useState(0);
  const [viewResetRevision, setViewResetRevision] = useState(0);
  const [analysisDetailOpen, setAnalysisDetailOpen] = useState(false);
  const refreshMarketResults = useCallback(() => setMarketRevision((current) => current + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    fetchMarkets(controller.signal).then(({ markets: choices }) => {
      setMarkets(choices);
      try {
        const previous = JSON.parse(sessionStorage.getItem("radar.explore.filters.v1") || "null") as { filters?: Filters; skill?: string } | null;
        const saved = previous?.filters?.market_id || localStorage.getItem("radar.market");
        if (saved && choices.some((market) => market.id === saved)) {
          const restored = { ...INITIAL_FILTERS, ...previous?.filters, market_id: saved };
          setFilters(restored); setDraftSearch(restored.search); setSelectedSkill(previous?.skill || null);
        }
      } catch { /* Storage is optional. */ }
      setMarketReady(true);
    }).catch((reason) => { if (reason.name !== "AbortError") { setStatusError("No se pudo cargar la lista de mercados."); setMarketReady(true); } });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!marketReady) return;
    try {
      localStorage.setItem("radar.market", marketId);
    } catch { /* Storage is optional. */ }
  }, [marketId, marketReady]);
  useEffect(() => {
    const onFocus = () => refreshMarketResults();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshMarketResults]);
  const changeMarket = (id: string) => {
    const next = { ...INITIAL_FILTERS, market_id: id };
    try { localStorage.setItem("radar.market", id); } catch { /* Storage is optional. */ }
    setFilters(next); setDraftSearch(next.search); setSelectedSkill(null); setSelectedId(null);
    setJobs([]); setSkillOverview(null); setChatJobs([]); setSelectedDistrictKey(null);
    setShowFavorites(false); setShowHidden(false);
  };
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
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [radarCenter, setRadarCenter] = useState({ longitude: -77.043, latitude: -12.046 });
  const [radarRadiusKm, setRadarRadiusKm] = useState<number>(5);
  const [radarDistrictKey, setRadarDistrictKey] = useState<string | null>(null);
  const [radarCenterOpen, setRadarCenterOpen] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [showFavorites, setShowFavorites] = useState(false);
  const [chatJobs, setChatJobs] = useState<Job[]>([]); // ofertas abiertas desde el chat que no estaban en ningún listado
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [activeView, setActiveView] = useState<RadarView>("map");
  const [studioJobId, setStudioJobId] = useState<string | null>(null);
  const [studioContext, setStudioContext] = useState<AgentContext["cvStudio"] | null>(null);
  const [applicationsContext, setApplicationsContext] = useState<{ count: number; status: string } | null>(null);
  const onApplicationsContext = useCallback((count: number, status: string) => setApplicationsContext((current) => (current && current.count === count && current.status === status ? current : { count, status })), []);
  const [analysisContext, setAnalysisContext] = useState<AgentContext["analysis"]>({ ready: false, updatedAt: new Date(0).toISOString(), windows: [], recentQueries: [] });
  const lastMapMode = useRef<"heatmap" | "radar">("heatmap");
  const [statusBusy, setStatusBusy] = useState(false);
  const [removedIds, setRemovedIds] = useState<ReadonlySet<string>>(() => new Set());
  const [, setFavoriteBusy] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [offerPanelHeight, setOfferPanelHeight] = useState<number | null>(null);
  const offerPanelRef = useRef<HTMLDivElement | null>(null);
  const offerResizeRef = useRef<{ startY: number; startHeight: number; lastY: number; frame: number | null } | null>(null);
  const [expandedDescriptionId, setExpandedDescriptionId] = useState<string | null>(null);
  const [radarLabel, setRadarLabel] = useState<string | null>(null);
  const [toast, setToast] = useState<{ id: number; message: string; undo?: () => void } | null>(null);
  const [descriptions, setDescriptions] = useState<Record<string, string | null>>({});
  const baseJob = useMemo(() => [...jobs, ...hiddenJobs, ...favoriteJobs, ...chatJobs].find((job) => job.id === selectedId) || null, [chatJobs, favoriteJobs, hiddenJobs, jobs, selectedId]);
  // Los listados llegan sin descripción (slim): se pide la de la oferta abierta y se guarda en memoria.
  useEffect(() => {
    if (!baseJob || baseJob.description !== undefined || descriptions[baseJob.id] !== undefined) return;
    const controller = new AbortController();
    fetchJobDescription(baseJob.id, controller.signal)
      .then((text) => setDescriptions((current) => ({ ...current, [baseJob.id]: text })))
      .catch(() => {});
    return () => controller.abort();
  }, [baseJob, descriptions]);
  const selectedJob = useMemo(
    () => baseJob ? { ...baseJob, description: baseJob.description !== undefined ? baseJob.description : (descriptions[baseJob.id] === undefined ? "_Cargando descripción…_" : descriptions[baseJob.id]) } : null,
    [baseJob, descriptions],
  );

  const salaryRangeInvalid = filters.min_salary !== "" && filters.max_salary !== "" && Number(filters.min_salary) > Number(filters.max_salary);
  useEffect(() => {
    if (!marketReady) return;
    if (salaryRangeInvalid) { setError("El sueldo mínimo no puede superar el máximo."); setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const queryFilters = { ...filters };
    fetchJobs(selectedSkill ? { ...queryFilters, skill: selectedSkill } : queryFilters, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setJobs(result); })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError("No se pudieron cargar las ofertas. Recarga Radar; si hay una captura activa, espera a que termine.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [filters, selectedSkill, marketReady, salaryRangeInvalid, marketRevision]);

  useEffect(() => {
    if (!filtersOpen) return;
    const controller = new AbortController();
    setSkillsLoading(true);
    setSkillOverview(null);
    fetchSkillOverview(filters, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setSkillOverview(result); })
      .catch(() => {})
      .finally(() => { if (!controller.signal.aborted) setSkillsLoading(false); });
    return () => controller.abort();
  }, [filtersOpen, filters, mode]);

  const activeBaseJobs = useMemo(
    () => jobs.filter((job) => !APPLIED_STATES.includes(job.user_application || "") && job.user_status !== "hidden" && !removedIds.has(job.id)),
    [jobs, removedIds],
  );
  const portalJobs = activeBaseJobs;
  const districtStats = useMemo<DistrictSummary[]>(() => {
    const groups = new Map<string, DistrictSummary>();
    for (const job of portalJobs) {
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
  }, [portalJobs]);
  const visibleJobs = useMemo(
    () => {
      if (mode === "radar") {
        if (!radarDistrictKey) return [];
        return portalJobs
          .filter((job) => job.latitude !== null && job.longitude !== null)
          .map((job) => ({ ...job, distance_km: distanceKm(radarCenter, { latitude: job.latitude as number, longitude: job.longitude as number }) }))
          .filter((job) => job.distance_km <= radarRadiusKm)
          .sort((a, b) => a.distance_km - b.distance_km);
      }
      return selectedDistrictKey ? portalJobs.filter((job) => districtKey(job.district) === selectedDistrictKey) : portalJobs;
    },
    [mode, portalJobs, radarCenter, radarRadiusKm, radarDistrictKey, selectedDistrictKey],
  );
  const selectedDistrict = districtStats.find((district) => district.key === selectedDistrictKey) || null;
  const radarDistrict = districtStats.find((district) => district.key === radarDistrictKey) || null;
  // En modo "jobs" no hay distrito elegido en el mapa (se limpia al entrar a esa vista): el distrito de contexto
  // pasa a ser el de la oferta abierta, para no dejar al agente sin saberlo mientras la lee.
  const jobDistrict = mode === "jobs" && selectedJob?.district ? districtStats.find((district) => district.key === districtKey(selectedJob.district)) || null : null;
  const browsedDistrict = selectedDistrict || jobDistrict;
  const agentContext = useMemo<AgentContext>(() => ({
    screen: activeView,
    mode: activeView === "map" ? (mode === "heatmap" ? "districts" : mode === "radar" ? "radar" : "jobs") : undefined,
    district: (mode === "radar" ? radarDistrict?.district : browsedDistrict?.district) || undefined,
    radar: mode === "radar" && radarDistrict ? { center: radarDistrict.district, radiusKm: radarRadiusKm } : undefined,
    filters: activeView === "applications" ? (applicationsContext ? { status: applicationsContext.status } : undefined) : Object.fromEntries([...Object.entries(filters).filter(([key, value]) => key === "relevance_tier" || Boolean(value)), ...(selectedSkill ? [["skill", selectedSkill]] : [])]),
    selectedJob: selectedJob ? { id: selectedJob.id, title: selectedJob.title, company: selectedJob.company || undefined, district: selectedJob.district || undefined } : undefined,
    visibleCount: activeView === "applications" ? applicationsContext?.count : visibleJobs.length,
    districtJobs: mode === "radar" ? undefined : browsedDistrict?.count,
    analysis: activeView === "analysis" ? analysisContext : undefined,
    cvStudio: activeView === "cvs" ? studioContext ?? undefined : undefined,
  }), [activeView, analysisContext, applicationsContext, studioContext, browsedDistrict, filters, mode, radarDistrict, radarRadiusKm, selectedJob, selectedSkill, visibleJobs.length]);
  useEffect(() => { onAgentContextChange?.(agentContext); }, [agentContext, onAgentContextChange]);
  const radarRadiusCounts = useMemo(
    () => RADAR_RADII.map((radius) => ({ radius, count: radarDistrictKey ? portalJobs.filter((job) => job.latitude !== null && job.longitude !== null && distanceKm(radarCenter, { latitude: job.latitude, longitude: job.longitude }) <= radius).length : 0 })),
    [portalJobs, radarCenter, radarDistrictKey],
  );
  const radarCountsMap = useMemo(() => Object.fromEntries(radarRadiusCounts.map((item) => [item.radius, item.count])), [radarRadiusCounts]);
  const archivedJobs = hiddenJobs;
  const listedJobs = showHidden ? archivedJobs : showFavorites ? favoriteJobs : visibleJobs;
  const signalJobs = listedJobs;
  const {
    items: pagedJobs, items2: pagedJobsMap, containerRef, containerRef2,
    spacerHeight, spacerHeight2, bottomSpacerHeight, bottomSpacerHeight2, trimmed, trimmed2,
  } = useProgressiveList(listedJobs, selectedId);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast((current) => current?.id === toast.id ? null : current), 6000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented) return;
      if (event.key === "Escape" && filtersOpen && !(event.target as HTMLElement | null)?.closest('[role="dialog"]')) {
        setFiltersOpen(false);
        return;
      }
      if (activeView !== "map") return;
      const target = event.target as HTMLElement | null;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (target?.closest('[role="dialog"]')) return;
      if (target && (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName))) return;
      const index = listedJobs.findIndex((job) => job.id === selectedId);
      const current = index >= 0 ? listedJobs[index] : null;
      if (event.key === "j" || event.key === "k") {
        const next = listedJobs[Math.min(Math.max(index + (event.key === "j" ? 1 : -1), 0), listedJobs.length - 1)];
        if (next) { event.preventDefault(); selectJob(next); }
      } else if (event.key === "u" && toast?.undo) {
        event.preventDefault();
        toast.undo();
      } else if (current && event.key === "f") {
        event.preventDefault();
        void toggleFavorite(current);
      } else if (current && event.key === "x" && !showHidden) {
        event.preventDefault();
        const next = listedJobs[index + 1] || listedJobs[index - 1];
        void hideJob(current).then(() => { if (next) setSelectedId(next.id); });
      } else if (current && event.key === "r" && showHidden) {
        event.preventDefault();
        void restoreJob(current);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });


  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters((current) => ({ ...current, search: draftSearch.trim() }));
  }

  function updateFilter(key: keyof Filters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  const selectJob = useCallback((job: Job) => {
    setSelectedId(job.id);
    setExpandedDescriptionId(null);
    if (mode === "heatmap") setSelectedDistrictKey(districtKey(job.district));
  }, [mode]);

  function selectDistrict(key: string) {
    setSelectedDistrictKey((current) => current === key ? null : key);
    setSelectedId(null);
  }

  async function switchView(view: "active" | "favorites" | "hidden") {
    setStatusError(null);
    try {
      if (view === "hidden") setHiddenJobs(await fetchHiddenJobs());
      // Siempre se relee: una oferta oculta o postulada no debe seguir apareciendo en ★.
      if (view === "favorites") setFavoriteJobs(await fetchInterestJobs());
    } catch {
      setStatusError(view === "hidden" ? "No se pudieron cargar las ofertas ocultas." : "No se pudieron cargar los favoritos.");
      return;
    }
    setShowHidden(view === "hidden");
    setShowFavorites(view === "favorites");
    setSelectedId(null);
  }

  function notify(message: string, undo?: () => void) {
    setToast({ id: Date.now(), message, undo });
  }

  const toggleFavorite = useCallback(async (job: Job) => {
    const nextValue = !job.is_favorite;
    setFavoriteBusy(true);
    setStatusError(null);
    try {
      await updateJobFavorite(job.id, nextValue);
      const update = (item: Job) => item.id === job.id ? { ...item, is_favorite: nextValue } : item;
      setJobs((current) => current.map(update));
      setHiddenJobs((current) => current.map(update));
      setFavoriteJobs((current) => {
        const without = current.filter((item) => item.id !== job.id);
        // Una oferta oculta no entra a ★: el archivo es su único lugar.
        return nextValue && job.user_status !== "hidden" ? [{ ...job, is_favorite: true }, ...without] : without;
      });
      if (!nextValue && showFavorites) setSelectedId(null);
    } catch {
      setStatusError(nextValue ? "No se pudo guardar el favorito." : "No se pudo quitar el favorito.");
    } finally {
      setFavoriteBusy(false);
    }
  }, [showFavorites]);

  // Hide and "applied" update the UI first (the API can be slow while an ingestion holds the database) and roll back on failure.
  const forgetJob = useCallback((id: string) => {
    setRemovedIds((current) => new Set(current).add(id));
    setJobs((current) => current.filter((job) => job.id !== id));
    setFavoriteJobs((current) => current.filter((job) => job.id !== id));
    setSelectedId((current) => current === id ? null : current);
  }, []);
  const unforgetJob = useCallback((job: Job) => {
    setRemovedIds((current) => { const next = new Set(current); next.delete(job.id); return next; });
    setJobs((current) => current.some((item) => item.id === job.id) ? current : [...current, job]);
  }, []);

  async function hideJob(target: Job) {
    setStatusError(null);
    forgetJob(target.id);
    setHiddenJobs((current) => [{ ...target, user_status: "hidden", user_reason: "not_interested" }, ...current.filter((job) => job.id !== target.id)]);
    notify("[ok] oferta archivada", () => void restoreJob(target));
    try {
      await updateJobStatus(target.id, "hidden", "not_interested");
    } catch {
      unforgetJob(target);
      setHiddenJobs((current) => current.filter((job) => job.id !== target.id));
      setToast(null);
      setStatusError("No se pudo ocultar la oferta.");
    }
  }

  async function markApplied(target: Job) {
    setStatusError(null);
    forgetJob(target.id);
    // Solo se confirma: la postulación queda en Mi búsqueda, sin cambiar de vista.
    notify("[ok] postulación guardada en Mi búsqueda");
    try {
      await updateApplication(target.id, "applied");
      if (target.is_favorite) await updateJobFavorite(target.id, false);
      window.dispatchEvent(new CustomEvent("radar:jobs-changed"));
    } catch {
      unforgetJob(target);
      setToast(null);
      setStatusError("No se pudo guardar la postulación.");
    }
  }

  async function restoreJob(job: Job) {
    setStatusBusy(true);
    setStatusError(null);
    try {
      await updateJobStatus(job.id, "visible");
      setRemovedIds((current) => { const next = new Set(current); next.delete(job.id); return next; });
      setHiddenJobs((current) => current.filter((item) => item.id !== job.id));
      if (showHidden) setSelectedId(null);
      const refreshed = await fetchJobs(filters);
      if (currentFiltersRef.current === filters) setJobs(refreshed);
      setToast(null);
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
    setRadarLabel(null);
    setRadarCenterOpen(false);
    setSelectedId(null);
  }

  const pickRadarCenter = useCallback((center: { longitude: number; latitude: number }, label: string) => {
    if (districtStats.length === 0) return;
    const nearest = districtStats.reduce((best, item) => distanceKm(center, item) < distanceKm(center, best) ? item : best);
    setRadarDistrictKey(nearest.key);
    setRadarCenter(center);
    setRadarLabel(label);
    setRadarCenterOpen(false);
    setSelectedId(null);
  }, [districtStats]);

  const [locating, setLocating] = useState(false);
  function locateMe() {
    if (!navigator.geolocation) { notify("[err] tu navegador no soporta geolocalización"); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => { setLocating(false); pickRadarCenter({ longitude: position.coords.longitude, latitude: position.coords.latitude }, "Mi ubicación"); },
      (error) => { setLocating(false); notify(error.code === 1 ? "Permiso de ubicación denegado. Elige un distrito o pulsa el mapa." : "No se pudo obtener tu ubicación. Elige un distrito o pulsa el mapa."); },
      { timeout: 8000 },
    );
  }

  function changeMode(nextMode: MapMode) {
    setFiltersOpen(false);
    setMode(nextMode);
    setRadarCenterOpen(false);
    setSelectedId(null);
    if (nextMode !== "heatmap") setSelectedDistrictKey(null);
    if (nextMode === "heatmap" || nextMode === "radar") lastMapMode.current = nextMode;
    if (nextMode === "radar") {
      setRadarDistrictKey(null);
      setRadarLabel(null);
      setRadarCenter({ longitude: -77.043, latitude: -12.046 });
    }
  }


  useEffect(() => {
    function onJobsChanged() {
      refreshMarketResults();
      if (showFavorites) void fetchInterestJobs().then(setFavoriteJobs).catch(() => undefined);
      if (showHidden) void fetchHiddenJobs().then(setHiddenJobs).catch(() => undefined);
    }
    window.addEventListener("radar:jobs-changed", onJobsChanged);
    return () => window.removeEventListener("radar:jobs-changed", onJobsChanged);
  }, [filters, showFavorites, showHidden, refreshMarketResults]);

  function selectView(view: RadarView) {
    setActiveView(view);
    setRadarCenterOpen(false);
    setSelectedId(null);
    if (view === "map") {
      setMode(lastMapMode.current);
      return;
    }
    setFiltersOpen(false);
    setMode(view);
  }

  // Un enlace del chat (`radar:job:<id>`) abre la oferta en el detalle del mapa, aunque no esté en la vista actual.
  const openJobFromChat = useCallback(async (id: string) => {
    let job = [...jobs, ...hiddenJobs, ...favoriteJobs, ...chatJobs].find((item) => item.id === id) ?? null;
    if (!job) {
      try { job = await fetchJob(id); } catch { job = null; }
      if (!job) { setStatusError("No se encontró esa oferta (pudo haber sido eliminada)."); return; }
      const found = job;
      setChatJobs((current) => [found, ...current.filter((item) => item.id !== found.id)]);
    }
    selectViewRef.current("map");
    setSelectedId(job.id);
    if (lastMapMode.current !== "radar" && job.district) setSelectedDistrictKey(districtKey(job.district));
    setExpandedDescriptionId(null);
  }, [chatJobs, favoriteJobs, hiddenJobs, jobs]);
  const selectViewRef = useRef(selectView);
  useEffect(() => { selectViewRef.current = selectView; });
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("view") === "cvs") {
      selectViewRef.current("cvs");
      url.searchParams.delete("view");
      window.history.replaceState(window.history.state, "", url);
    }
  }, []);
  useEffect(() => {
    const prepare = (event: Event) => {
      const id = (event as CustomEvent<{ jobId?: string }>).detail?.jobId;
      if (typeof id !== "string" || !id) return;
      setStudioJobId(id); selectViewRef.current("cvs");
    };
    const profile = () => { setStudioJobId(null); selectViewRef.current("cvs"); };
    window.addEventListener(PREPARE_CV_EVENT, prepare);
    window.addEventListener(MY_CV_EVENT, profile);
    return () => { window.removeEventListener(PREPARE_CV_EVENT, prepare); window.removeEventListener(MY_CV_EVENT, profile); };
  }, []);
  useEffect(() => {
    const onOpen = (event: Event) => { const id = (event as CustomEvent<{ id?: string }>).detail?.id; if (id) void openJobFromChat(id); };
    window.addEventListener(OPEN_JOB_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_JOB_EVENT, onOpen);
  }, [openJobFromChat]);

  // Filtros es una capa global: abrirla o cerrarla no cambia de vista ni pierde estado.
  const filtersAvailable = activeView === "map" || activeView === "analysis";

  function resetExploreView() {
    setFilters({ ...INITIAL_FILTERS, market_id: marketId });
    setDraftSearch("");
    setSelectedSkill(null);
    setSelectedDistrictKey(null);
    setRadarDistrictKey(null);
    setRadarLabel(null);
    setRadarCenterOpen(false);
    setRadarRadiusKm(5);
    setRadarCenter({ longitude: -77.043, latitude: -12.046 });
    setShowFavorites(false);
    setShowHidden(false);
    setSelectedId(null);
    setExpandedDescriptionId(null);
    setFiltersOpen(false);
    setStatusError(null);
    lastMapMode.current = "heatmap";
    if (activeView === "map") setMode("heatmap");
    setViewResetRevision((value) => value + 1);
    document.querySelector<HTMLButtonElement>('.edge-menu-toggle[aria-controls="radar-controls-panel"]')?.focus({ preventScroll: true });
  }

  function restoreAnalysisScope(scope: AnalysisScope) {
    if (!markets.some((market) => market.id === scope.market_id)) { setStatusError("El mercado de esta vista ya no está disponible."); return; }
    const next = filtersFromScope(scope);
    setFilters(next); setDraftSearch(next.search); setSelectedSkill(scope.skill || null);
    setSelectedDistrictKey(scope.district ? districtKey(scope.district) : null);
    if (scope.radius_km != null && scope.latitude != null && scope.longitude != null) {
      lastMapMode.current = "radar";
      setRadarCenter({ latitude: scope.latitude, longitude: scope.longitude });
      setRadarRadiusKm(scope.radius_km); setRadarDistrictKey("saved-center"); setRadarLabel("Centro guardado");
    } else {
      lastMapMode.current = scope.empty ? "radar" : "heatmap";
      setRadarDistrictKey(null); setRadarLabel(null);
    }
    setSelectedId(null);
  }

  useEffect(() => {
    function applyResize() {
      const resize = offerResizeRef.current;
      const panel = offerPanelRef.current;
      if (resize) resize.frame = null;
      if (!resize || !panel) return;
      const maxHeight = Math.max(180, window.innerHeight - (window.innerHeight <= 460 ? 120 : 270));
      const next = Math.max(180, Math.min(maxHeight, resize.startHeight + resize.startY - resize.lastY));
      panel.style.height = `${next}px`;
    }
    function resizeOffers(event: PointerEvent) {
      const resize = offerResizeRef.current;
      if (!resize) return;
      resize.lastY = event.clientY;
      if (resize.frame !== null) return;
      resize.frame = requestAnimationFrame(applyResize);
    }
    function stopResizingOffers() {
      const resize = offerResizeRef.current;
      const panel = offerPanelRef.current;
      if (resize && resize.frame !== null) cancelAnimationFrame(resize.frame);
      if (panel) {
        panel.classList.remove("is-resizing");
        setOfferPanelHeight(panel.getBoundingClientRect().height);
      }
      document.body.classList.remove("is-resizing");
      offerResizeRef.current = null;
    }
    window.addEventListener("pointermove", resizeOffers, { passive: true });
    window.addEventListener("pointerup", stopResizingOffers, { passive: true });
    return () => {
      window.removeEventListener("pointermove", resizeOffers);
      window.removeEventListener("pointerup", stopResizingOffers);
    };
  }, []);

  function startOfferResize(event: ReactPointerEvent<HTMLDivElement>) {
    const panel = event.currentTarget.parentElement as HTMLDivElement | null;
    if (!panel) return;
    event.preventDefault();
    offerPanelRef.current = panel;
    panel.classList.add("is-resizing");
    document.body.classList.add("is-resizing");
    offerResizeRef.current = { startY: event.clientY, startHeight: panel.getBoundingClientRect().height, lastY: event.clientY, frame: null };
  }

  const activeFilterCount = Object.entries(filters).filter(([key, value]) =>
    !["market_id", "profile_mode", "geo_scope"].includes(key) && (value || "") !== (INITIAL_FILTERS[key as keyof Filters] || ""),
  ).length + (selectedSkill ? 1 : 0);
  const marketLabel = marketId === "industrial_engineering" ? "Industrial"
    : marketId === "sistemas_software" ? "Sistemas y Software" : currentMarket?.name || "Mercado";

  const analysisMapMode = mode === "heatmap" || mode === "radar" ? mode : lastMapMode.current;
  const canResetExplore = activeFilterCount > 0 || draftSearch !== filters.search || Boolean(selectedDistrictKey) ||
    analysisMapMode === "radar" || filters.profile_mode !== INITIAL_FILTERS.profile_mode ||
    filters.geo_scope !== INITIAL_FILTERS.geo_scope ||
    (activeView === "map" && (showFavorites || showHidden || selectedId !== null)) ||
    (activeView === "analysis" && analysisDetailOpen);
  const analysisQueryScope = useMemo<AnalysisScope>(() => ({
    ...analysisScope(filters, selectedSkill),
    ...(analysisMapMode === "radar"
      ? radarDistrictKey ? { latitude: radarCenter.latitude, longitude: radarCenter.longitude, radius_km: radarRadiusKm } : { empty: true }
      : selectedDistrictKey ? { district: selectedDistrictKey } : {}),
  }), [filters, selectedSkill, radarCenter, radarRadiusKm, radarDistrictKey, selectedDistrictKey, analysisMapMode]);
  useEffect(() => {
    if (!marketReady) return;
    try { sessionStorage.setItem("radar.explore.filters.v1", JSON.stringify({ filters, skill: selectedSkill })); } catch { /* Storage is optional. */ }
  }, [filters, selectedSkill, marketReady]);
  const analysisLabels = useMemo(() => {
    const labels = [marketLabel, `${filters.max_age_days} días`, "Lima/Callao"];
    if (analysisQueryScope.radius_km) labels.push(`${radarLabel || radarDistrict?.district || "Centro del radar"} · ${radarRadiusKm} km`);
    else if (analysisQueryScope.empty) labels.push("Radar sin centro");
    else if (selectedDistrictKey) labels.push(selectedDistrict?.district || selectedDistrictKey);
    for (const key of ["area", "source", "search", "seniority", "work_mode"] as const) if (filters[key]) labels.push(SCOPE_LABELS[filters[key]!] || filters[key]!);
    if (selectedSkill) labels.push(SCOPE_LABELS[selectedSkill] || selectedSkill);
    if (filters.min_salary || filters.max_salary) labels.push(`Sueldo ${filters.min_salary || "sin mínimo"}–${filters.max_salary || "sin máximo"}`);
    if (filters.relevance_tier !== "market") labels.push(SCOPE_LABELS[filters.relevance_tier || ""] || "Incluye otros mercados");
    if (filters.profile_mode === "saved") labels.push("Perfil de búsqueda");
    return labels;
  }, [analysisQueryScope, marketLabel, filters, radarLabel, radarDistrict, radarRadiusKm, selectedDistrictKey, selectedDistrict, selectedSkill]);

  return (
    <main className="radar-shell radar-minimal">
      <section className="workspace">
        {filtersAvailable && <div className="explore-controls">
          {canResetExplore && <button className="edge-menu-toggle explore-reset" type="button" aria-label="Restablecer vista" title="Restablecer vista" onClick={resetExploreView}>
            <span aria-hidden="true">↺</span>
          </button>}
          <button className={`edge-menu-toggle ${filtersOpen ? "is-open" : ""}`} type="button" aria-expanded={filtersOpen} aria-controls="radar-controls-panel" onClick={() => setFiltersOpen((current) => !current)}>
            <span aria-hidden="true">{filtersOpen ? "×" : "☷"}</span>
            <small>{filtersOpen ? "Cerrar" : "Filtros"}{!filtersOpen && activeFilterCount > 0 ? ` · ${activeFilterCount}` : ""}</small>
          </button>
        </div>}
        <nav className="mode-rail" aria-label="Vistas">
          <button className={activeView === "map" ? "active" : ""} type="button" aria-label="Mapa" title="Mapa" onClick={() => selectView("map")}><span aria-hidden="true">◎</span></button>
          <button className={activeView === "analysis" ? "active" : ""} type="button" aria-label="Análisis" title="Análisis" onClick={() => selectView("analysis")}><span aria-hidden="true">▦</span></button>
          <button className={activeView === "applications" ? "active" : ""} type="button" aria-label="Mi búsqueda" title="Mi búsqueda" onClick={() => selectView("applications")}><span aria-hidden="true">✓</span></button>
        </nav>
        <aside id="radar-controls-panel" className={`sidebar tool-${filtersAvailable && filtersOpen ? "filters" : activeView !== "map" ? "analysis" : mode === "radar" ? "radar" : "districts"} ${(filtersAvailable && filtersOpen) || (activeView === "map" && mode === "radar") ? "is-open" : ""}`}>
          <MarketControls markets={markets} marketId={marketId} onMarket={changeMarket} />
          <form className="search-box" onSubmit={submitSearch}><span>⌕</span><input value={draftSearch} onChange={(event) => setDraftSearch(event.target.value)} placeholder="Cargo, empresa o palabra clave" aria-label="Buscar ofertas" /><button type="submit" aria-label="Buscar">↵</button></form>

          <div className="primary-filters"><label>Área profesional<select value={filters.area} onChange={(event) => updateFilter("area", event.target.value)}>{areas.map((area) => <option key={area} value={area}>{area || "Todas"}</option>)}</select></label><label>Antigüedad<select value={filters.max_age_days} onChange={(event) => updateFilter("max_age_days", event.target.value)}><option value="7">7 días</option><option value="14">14 días</option><option value="30">30 días</option><option value="90">90 días</option></select></label></div>
          <div className="filter-summary"><span>{activeFilterCount ? `${activeFilterCount} ${activeFilterCount === 1 ? "filtro modificado" : "filtros modificados"}` : "Todos los criterios"}</span>{activeFilterCount > 0 && <button type="button" className="clear-all-filters" onClick={() => { setFilters({ ...INITIAL_FILTERS, market_id: marketId }); setDraftSearch(""); setSelectedSkill(null); }}>Limpiar</button>}</div>
          <details className="market-extra-filters"><summary>Más filtros</summary><div className="filter-section">
            <label>Relevancia<select value={filters.relevance_tier || ""} onChange={(event) => updateFilter("relevance_tier", event.target.value)}><option value="market">Todo el mercado</option><option value="target">Puestos priorizados del mercado</option><option value="core">Núcleo del mercado</option><option value="adjacent">Áreas relacionadas</option><option value="out_of_focus">Fuera de foco</option><option value="">Incluir ofertas ajenas al mercado</option></select></label>

            <div className="two-columns"><label>Seniority<select value={filters.seniority} onChange={(event) => updateFilter("seniority", event.target.value)}><option value="">Todos</option><option value="intern">Intern</option><option value="junior">Junior</option><option value="mid">Intermedio</option><option value="senior">Senior</option></select></label><label>Modalidad<select value={filters.work_mode} onChange={(event) => updateFilter("work_mode", event.target.value)}><option value="">Todas</option><option value="onsite">Presencial</option><option value="hybrid">Híbrido</option><option value="remote">Remoto</option></select></label></div>
            <fieldset className="salary-range"><legend>Sueldo publicado</legend><div className="two-columns"><label>Desde<input aria-label="Sueldo desde" type="number" min="0" placeholder="Sin mínimo" value={filters.min_salary} onChange={(event) => updateFilter("min_salary", event.target.value)} /></label><label>Hasta<input aria-label="Sueldo hasta" type="number" min="0" placeholder="Sin máximo" value={filters.max_salary} onChange={(event) => updateFilter("max_salary", event.target.value)} /></label></div><small>{salaryRangeInvalid ? "El mínimo no puede superar el máximo." : "Con un límite, se omiten ofertas sin sueldo publicado."}</small></fieldset>
            <div className="two-columns"><label>Portal<select value={filters.source || ""} onChange={(event) => updateFilter("source", event.target.value)}><option value="">Todos</option><option value="indeed">Indeed</option><option value="computrabajo">Computrabajo</option><option value="linkedin">Linkedin</option><option value="google">Google Jobs</option><option value="bumeran">Bumeran</option><option value="laborum">Laborum</option><option value="empleos">Empleos Perú</option></select></label><label>Competencia<select value={selectedSkill || ""} onChange={(event) => { setSelectedSkill(event.target.value || null); setSelectedId(null); }}><option value="">Todas</option>{selectedSkill && !skillOverview?.skills.some((skill) => skill.name === selectedSkill) && <option value={selectedSkill}>{SCOPE_LABELS[selectedSkill] || selectedSkill}</option>}{skillsLoading && <option disabled>Cargando…</option>}{(skillOverview?.skills || []).map((skill) => <option key={skill.name} value={skill.name}>{SCOPE_LABELS[skill.name] || skill.name}</option>)}</select></label></div>
          </div></details>

          <div className="map-mode"><div className="section-label">Visualización</div><div className="segmented">{([["jobs", "Ofertas"], ["heatmap", "Distritos"], ["radar", "Radar"]] as const).map(([value, label]) => <button key={value} className={mode === value ? "active" : ""} onClick={() => changeMode(value)} type="button">{label}</button>)}</div>{mode === "radar" && <div className="radar-controls"><div className="radar-center-control"><span>Centro del radar</span><div className="radar-center-select"><button className={radarCenterOpen ? "open" : ""} type="button" aria-haspopup="listbox" aria-expanded={radarCenterOpen} onClick={() => setRadarCenterOpen((current) => !current)}>{radarDistrict ? `${radarDistrict.district} · ${radarDistrict.count} ofertas` : "Selecciona un distrito"}<b>⌄</b></button>{radarCenterOpen && <div className="radar-center-menu" role="listbox" aria-label="Centro del radar">{districtStats.map((district) => <button key={district.key} className={radarDistrictKey === district.key ? "active" : ""} type="button" role="option" aria-selected={radarDistrictKey === district.key} onClick={() => selectRadarDistrict(district.key)}>{district.district}<span>{district.count} ofertas</span></button>)}</div>}</div></div><div className="radar-locate-row"><button className="radar-locate" type="button" disabled={locating} onClick={locateMe}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M12 2v4M12 18v4M2 12h4M18 12h4" /></svg>{locating ? "Localizando…" : "Mi ubicación"}</button><small>o elige un punto en el mapa</small></div><span className="radar-readout">Ubicación aproximada · {visibleJobs.length} ofertas</span><label className="radar-radius-select">Radio<select aria-label="Radio del radar" value={radarRadiusKm} onChange={(event) => { setRadarRadiusKm(Number(event.target.value)); setSelectedId(null); }}>{radarRadiusCounts.map(({ radius, count }) => <option key={radius} value={radius}>{radius} km · {count} ofertas</option>)}</select></label></div>}</div>
          {mode === "jobs" && <>
          <div className="job-list-header"><span>{showHidden ? "Ofertas ocultas" : showFavorites ? "Favoritos" : selectedSkill ? `Ofertas con ${selectedSkill}` : selectedDistrict ? `Ofertas en ${selectedDistrict.district}` : "Ofertas recientes"}</span><div className="job-list-tools"><span>{loading && jobs.length === 0 && !showHidden && !showFavorites ? "…" : `${showHidden ? archivedJobs.length : showFavorites ? favoriteJobs.length : visibleJobs.filter((job) => job.latitude !== null && job.longitude !== null).length} ${showHidden ? "archivadas" : showFavorites ? "guardadas" : "en mapa"}`}</span>{selectedSkill && !showHidden && !showFavorites && <button className="clear-skill-filter" type="button" onClick={() => setSelectedSkill(null)} aria-label="Quitar filtro de competencia" title="Quitar filtro de competencia">×</button>}</div></div>
          <div className="view-tabs" role="tablist" aria-label="Vista de ofertas">{([["active", "activas", !showHidden && !showFavorites], ["favorites", "★ fav", showFavorites], ["hidden", "archivo", showHidden]] as const).map(([view, label, active]) => <button key={view} type="button" role="tab" aria-selected={active} className={`view-tab ${view} ${active ? "active" : ""}`} onClick={() => void switchView(view)}>{view === "hidden" && <IconEyeOff />}{label}</button>)}</div>

          {statusError && <div className="status-error">{statusError}</div>}
          <div className="job-list" ref={containerRef}>{loading && jobs.length === 0 && !showHidden && !showFavorites && <div className="empty-state">Buscando ofertas<LoadingDots /></div>}{!loading && error && !showHidden && !showFavorites && <div className="empty-state error-state">{error}</div>}{!loading && !error && listedJobs.length === 0 && <div className="empty-state">{showHidden ? "> archivo vacío" : showFavorites ? "> sin favoritos guardados" : "No hay ofertas con estos filtros. Prueba a limpiar los filtros o ampliar la antigüedad."}</div>}{trimmed && <div style={{ height: spacerHeight }} aria-hidden="true" />}{pagedJobs.map((job) => <JobCard key={job.id} job={job} selected={selectedId === job.id} showHidden={showHidden} onSelect={selectJob} onToggleFavorite={toggleFavorite} onMarkApplied={(target) => void markApplied(target)} onQuickHide={(target) => void hideJob(target)} onRestore={(target) => void restoreJob(target)} />)}{bottomSpacerHeight > 0 && <div style={{ height: bottomSpacerHeight }} aria-hidden="true" />}</div>
          </>}
        </aside>

        <section className={`map-panel ${mode === "jobs" ? "reading-panel" : mode === "analysis" || mode === "cvs" || mode === "applications" ? "analysis-mode-panel" : ""}`}>
          {mode === "jobs" ? (
            <JobReadingView
              selectedJob={selectedJob}

              statusBusy={statusBusy}
              onToggleFavorite={(job) => void toggleFavorite(job)}
              onMarkApplied={(job) => void markApplied(job)}
              onQuickHide={(job) => void hideJob(job)}
              onRestore={(job) => void restoreJob(job)}
            />
          ) : mode === "analysis" ? (
            <AnalysisView scope={analysisQueryScope} scopeLabels={analysisLabels} onContextChange={setAnalysisContext}
              resetRevision={viewResetRevision} onDetailOpenChange={setAnalysisDetailOpen}
              onRestoreScope={restoreAnalysisScope}
              onApplyChartFilter={(key, value) => {
                if (key === "skill") setSelectedSkill(value);
                else updateFilter(key, value);
              }} />
          ) : mode === "applications" ? (
            <ApplicationsView onContextChange={onApplicationsContext} />
          ) : mode === "cvs" ? (
            <CvView onStudioContext={setStudioContext} openJobId={studioJobId} onOpenJobConsumed={() => setStudioJobId(null)} />
          ) : (
            <>
              <div className="map-header">
                <div className="map-context">
                  {mode === "heatmap" ? <select aria-label="Distrito" value={selectedDistrictKey || ""} onChange={(event) => {
                    setSelectedDistrictKey(event.target.value || null); setSelectedId(null);
                  }}>
                    <option value="">Todos los distritos</option>
                    {selectedDistrictKey && !selectedDistrict && <option value={selectedDistrictKey}>{selectedDistrictKey} · 0</option>}
                    {districtStats.map((district) => <option key={district.key} value={district.key}>{district.district} · {district.count}</option>)}
                  </select> : <span className="radar-location">{radarLabel || radarDistrict?.district || "Lima y Callao"}</span>}
                  <small>{marketLabel} · {filters.max_age_days} días · Lima/Callao</small>
                </div>
                <div className="view-tabs map-view-toggle" role="tablist" aria-label="Tipo de mapa">{([["heatmap", "Distritos"], ["radar", "Radar"]] as const).map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={mode === value} className={`view-tab ${mode === value ? "active" : ""}`} onClick={() => changeMode(value)}>{label}</button>)}</div>
              </div>
              <div className={`map-wrap ${mode === "radar" ? "radar-active" : ""}`}>
                <MapView resetRevision={viewResetRevision} radarCounts={radarCountsMap} onPickRadarCenter={(center) => pickRadarCenter(center, "PUNTO EN MAPA")} jobs={mode === "radar" ? visibleJobs : portalJobs} mode={mode} radarCenter={radarCenter} radarRadiusKm={radarRadiusKm} radarDistrictKey={radarDistrictKey} selectedDistrictKey={selectedDistrictKey} onSelectJob={(jobId) => { const job = visibleJobs.find((item) => item.id === jobId); if (job) selectJob(job); }} onSelectDistrict={selectDistrict} />
                {(mode === "heatmap" || mode === "radar") && <aside className="offer-scroll" aria-label="Ofertas visibles" style={offerPanelHeight ? { height: `${offerPanelHeight}px` } : undefined}><div className="offer-resize-handle" role="separator" aria-label="Ajustar altura de ofertas" onPointerDown={startOfferResize} /><div className="offer-scroll-heading"><span title={currentMarket?.name}>{showHidden ? "Archivo" : showFavorites ? "Favoritos" : "Ofertas"}</span><div className="offer-scroll-tools"><strong>{loading && jobs.length === 0 && !showHidden && !showFavorites ? "…" : signalJobs.length.toString()}</strong><div className="view-tabs" role="tablist" aria-label="Vista de ofertas">{([["active", "activas", !showHidden && !showFavorites], ["favorites", "favoritos", showFavorites], ["hidden", "archivo", showHidden]] as const).map(([view, label, active]) => <button key={view} type="button" role="tab" aria-label={label} title={label} aria-selected={active} className={`view-tab ${view} ${active ? "active" : ""}`} onClick={() => void switchView(view)}><ViewIcon view={view} /></button>)}</div></div></div><div className="offer-scroll-list" ref={containerRef2}>{trimmed2 && <div style={{ height: spacerHeight2 }} aria-hidden="true" />}{pagedJobsMap.map((job) => <OfferSignalCard key={job.id} job={job} selected={selectedId === job.id} showHidden={showHidden} onSelect={selectJob} onToggleFavorite={toggleFavorite} onMarkApplied={(target) => void markApplied(target)} onQuickHide={(target) => void hideJob(target)} onRestore={(target) => void restoreJob(target)} />)}{bottomSpacerHeight2 > 0 && <div style={{ height: bottomSpacerHeight2 }} aria-hidden="true" />}{!loading && error && <span className="offer-scroll-empty" role="alert">{error}</span>}{!loading && !error && signalJobs.length === 0 && <span className="offer-scroll-empty">{showHidden ? "> archivo vacío" : showFavorites ? "> sin favoritos guardados" : "No hay ofertas con estos filtros. Amplía la antigüedad o limpia los filtros."}</span>}</div></aside>}
                {selectedJob && (
                  <MapJobPopover
                    selectedJob={selectedJob}
                    expandedDescriptionId={expandedDescriptionId}
                    statusBusy={statusBusy}
                    onClose={() => { setSelectedId(null); setExpandedDescriptionId(null); }}
                    onToggleDescription={(jobId) => setExpandedDescriptionId((current) => current === jobId ? null : jobId)}
                    onQuickHide={(job) => void hideJob(job)}
                    onMarkApplied={(job) => void markApplied(job)}
                    onRestore={(job) => void restoreJob(job)}
                  />
                )}
              </div>
            </>
          )}
        </section>

      </section>
      {toast && <div className="terminal-toast" role="status"><span>{toast.message}</span>{toast.undo && <button type="button" onClick={() => toast.undo?.()}>[u] deshacer</button>}</div>}
    </main>
  );
}
