"use client";

import dynamic from "next/dynamic";
import { FormEvent, memo, PointerEvent as ReactPointerEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchAppliedJobs, fetchFavoriteJobs, fetchHiddenJobs, fetchJobDescription, fetchJobs, fetchSkillOverview, updateApplication, updateJobFavorite, updateJobStatus } from "../lib/api";
import { useProgressiveList } from "./useProgressiveList";
import { districtKey } from "../lib/districts";
import type { DistrictSummary, Filters, Job, MapMode, SkillOverview } from "../types";
import AnalysisView from "./AnalysisView";
import ApplicationsView from "./ApplicationsView";
import CvView from "./CvView";
import BootScreen from "./BootScreen";
import type { AgentContext } from "../lib/mobile-api";

function LoadingDots() {
  return (
    <span className="loading-dots" aria-hidden="true">
      <i /><i /><i />
    </span>
  );
}

const MapView = dynamic(() => import("./MapView"), { ssr: false, loading: () => <div className="map-loading">Cargando mapa de Lima<LoadingDots /></div> });

const AREAS = ["", "Diseño y medición del trabajo", "Investigación de operaciones y optimización", "Ingeniería económica y control", "Facilities, energía y mantenimiento", "Calidad y confiabilidad", "Ergonomía y factores humanos", "Operaciones y productividad", "Supply Chain, logística y compras", "Ingeniería de gestión y proyectos", "Seguridad y riesgos", "Información, analítica y sistemas", "Diseño y manufactura", "Diseño de producto y desarrollo", "Ingeniería de sistemas"];
const INITIAL_FILTERS: Filters = { search: "", area: "", seniority: "", work_mode: "", min_salary: "", max_age_days: "7", source: "", relevance_tier: "core" };
const RADAR_RADII = [2, 5, 10] as const;
type RadarView = "map" | "analysis" | "cvs" | "applications";
type AnalysisFilterColumn = "area" | "skill" | "seniority" | "work_mode" | "district";

const SENIORITY_VALUES: Record<string, string> = { practicante: "intern", intern: "intern", junior: "junior", intermedio: "mid", mid: "mid", senior: "senior" };
const WORK_MODE_VALUES: Record<string, string> = { presencial: "onsite", onsite: "onsite", híbrido: "hybrid", hibrido: "hybrid", hybrid: "hybrid", remoto: "remote", remote: "remote" };

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

function sourceName(url: string | null) {
  if (!url) return "Fuente n/i";
  try {
    const host = new URL(url).hostname.toLowerCase().replace(/^www\./, "");
    if (host.includes("linkedin")) return "LinkedIn";
    if (host.includes("indeed")) return "Indeed";
    if (host.includes("computrabajo")) return "Computrabajo";
    if (host.includes("glassdoor")) return "Glassdoor";
    return host.split(".")[0] || "Fuente";
  } catch {
    return "Fuente n/i";
  }
}

function companyMapsUrl(job: Pick<Job, "company" | "district" | "location">) {
  if (!job.company?.trim()) return null;
  const query = [job.company.trim(), job.district || job.location || "Lima", "Perú"]
    .filter(Boolean)
    .join(", ");
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

function CompanyMapsLink({ job }: { job: Pick<Job, "company" | "district" | "location"> }) {
  const url = companyMapsUrl(job);
  if (!url) return null;
  return (
    <a
      className="company-map-link"
      href={url}
      target="_blank"
      rel="noreferrer"
      aria-label={`Buscar ${job.company} en Google Maps`}
      title="Buscar empresa en Google Maps"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      ⌖
    </a>
  );
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

const OfferSignalCard = memo(function OfferSignalCard({ job, selected, showHidden, onSelect, onToggleFavorite, onQuickHide, onRestore }: { job: Job; selected: boolean; showHidden: boolean; onSelect: (job: Job) => void; onToggleFavorite: (job: Job) => void; onQuickHide: (job: Job) => void; onRestore: (job: Job) => void }) {
  return (
    <article
      className={`offer-scroll-card ${selected ? "selected" : ""}`}
      role="button"
      tabIndex={0}
      aria-label={`Ver detalle de ${job.title}`}
      onClick={() => onSelect(job)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(job);
        }
      }}
    >
      <span className="offer-scroll-meta">
        <span className="offer-scroll-area-line"><span title={job.primary_area || "Sin área"}>{job.primary_area || "Sin área"}</span></span>
        <span className="offer-scroll-date">{formatDate(job.published_at)}</span>
      </span>
      {job.url ? <a className="offer-scroll-title" href={job.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>{job.title}</a> : <strong>{job.title}</strong>}
      <span className="offer-scroll-company">
        {job.company || "Empresa no indicada"}
        <CompanyMapsLink job={job} />
      </span>
      <span className="offer-scroll-footer">
        <span className="offer-scroll-location">⌖ {job.district || job.location || "Ubicación pendiente"}{job.distance_km !== undefined ? ` · ${job.distance_km.toFixed(1)} km` : ""}<span className="offer-scroll-source"> · {sourceName(job.url)}</span></span>
        <span className="offer-scroll-actions">
          <CardAction className="favorite-toggle" label={job.is_favorite ? "Quitar de favoritos (f)" : "Añadir a favoritos (f)"} onAction={() => onToggleFavorite(job)}>{job.is_favorite ? "★" : "☆"}</CardAction>
          {showHidden
            ? <CardAction className="card-action restore" label="Restaurar oferta (r)" onAction={() => onRestore(job)}><IconUndo /></CardAction>
            : <CardAction className="card-action hide" label="Ocultar oferta (x)" onAction={() => onQuickHide(job)}><IconEyeOff /></CardAction>}
        </span>
      </span>
    </article>
  );
});

function IconEyeOff() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18M10.6 6.2A9.9 9.9 0 0 1 12 6c6 0 9.5 6 9.5 6a16 16 0 0 1-3.2 3.7M6.6 7.6C4 9.3 2.5 12 2.5 12s3.5 6 9.5 6c1.5 0 2.8-.4 4-.9M9.9 9.9a2.5 2.5 0 0 0 3.2 3.2" /></svg>;
}

function IconUndo() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 7 4 12l5 5M4 12h10a6 6 0 0 1 6 6" /></svg>;
}

function ViewIcon({ view }: { view: "active" | "favorites" | "hidden" | "applied" }) {
  if (view === "applied") return <span aria-hidden="true">✓</span>;
  if (view === "favorites") return <span aria-hidden="true">★</span>;
  if (view === "hidden") return <IconEyeOff />;
  return <span aria-hidden="true">◉</span>;
}

const REASON_LABELS: Record<string, string> = { closed: "cerrada", not_interested: "sin interés", applied: "postulada", duplicate: "duplicada", other: "otro" };
const ARCHIVE_FILTERS: Array<[string, string]> = [["", "todas"], ["closed", "cerradas"], ["not_interested", "sin interés"], ["applied", "postuladas"], ["duplicate", "duplicadas"], ["other", "otro"]];

function CardAction({ label, className, onAction, children }: { label: string; className: string; onAction: () => void; children: React.ReactNode }) {
  return (
    <span
      className={className}
      role="button"
      tabIndex={0}
      aria-label={label}
      title={label}
      onClick={(event) => { event.stopPropagation(); onAction(); }}
      onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); onAction(); } }}
    >
      {children}
    </span>
  );
}

const JobCard = memo(function JobCard({ job, selected, showHidden, onSelect, onToggleFavorite, onQuickHide, onRestore }: { job: Job; selected: boolean; showHidden: boolean; onSelect: (job: Job) => void; onToggleFavorite: (job: Job) => void; onQuickHide: (job: Job) => void; onRestore: (job: Job) => void }) {
  return (
    <button className={`job-card ${selected ? "selected" : ""}`} onClick={() => onSelect(job)}>
      <div className="job-card-top">
        <span className="job-area" title={job.primary_area || "Sin área"}>{job.primary_area || "Sin área"}</span>
        <span className="job-date">{formatDate(job.published_at)}</span>
        <CardAction className="favorite-toggle" label={job.is_favorite ? "Quitar de favoritos" : "Añadir a favoritos"} onAction={() => onToggleFavorite(job)}>{job.is_favorite ? "★" : "☆"}</CardAction>
        {showHidden
          ? <CardAction className="card-action restore" label="Restaurar oferta (r)" onAction={() => onRestore(job)}><IconUndo /></CardAction>
          : <CardAction className="card-action hide" label="Ocultar oferta (x)" onAction={() => onQuickHide(job)}><IconEyeOff /></CardAction>}
      </div>
      <strong>{job.title}</strong>
      <span className="job-company">{job.company || "Empresa no indicada"}</span>
      <div className="job-meta">
        <span>⌖ {job.district || job.location || "Ubicación pendiente"}{job.distance_km !== undefined ? ` · ${job.distance_km.toFixed(1)} km` : ""}</span>
        <span>{job.work_mode === "hybrid" ? "Híbrido" : job.work_mode === "remote" ? "Remoto" : job.work_mode === "onsite" ? "Presencial" : "Modalidad n/i"}</span>
      </div>
      {showHidden && <span className="hidden-reason">{`> motivo=${REASON_LABELS[job.user_reason || ""] || "oculta"}`}</span>}
    </button>
  );
});

export default function RadarClient({ onAgentContextChange }: { onAgentContextChange?: (context: AgentContext) => void }) {
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
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [radarCenter, setRadarCenter] = useState({ longitude: -77.043, latitude: -12.046 });
  const [radarRadiusKm, setRadarRadiusKm] = useState<number>(5);
  const [radarDistrictKey, setRadarDistrictKey] = useState<string | null>(null);
  const [radarCenterOpen, setRadarCenterOpen] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [showFavorites, setShowFavorites] = useState(false);
  const [showApplied, setShowApplied] = useState(false);
  const [appliedJobs, setAppliedJobs] = useState<Job[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [activeView, setActiveView] = useState<RadarView>("map");
  const [studioJobId, setStudioJobId] = useState<string | null>(null);
  const [studioContext, setStudioContext] = useState<AgentContext["cvStudio"] | null>(null);
  const [applicationsContext, setApplicationsContext] = useState<{ count: number; status: string } | null>(null);
  const onApplicationsContext = useCallback((count: number, status: string) => setApplicationsContext((current) => (current && current.count === count && current.status === status ? current : { count, status })), []);
  const [appliedJobIds, setAppliedJobIds] = useState<Set<string>>(new Set());
  const [analysisContext, setAnalysisContext] = useState<AgentContext["analysis"]>({ ready: false, updatedAt: new Date(0).toISOString(), windows: [], recentQueries: [] });
  const lastMapMode = useRef<"heatmap" | "radar">("heatmap");
  const [railPeek, setRailPeek] = useState(false);
  const railPeekRef = useRef(false);
  const [hideReasonFor, setHideReasonFor] = useState<string | null>(null);
  const [hideReason, setHideReason] = useState("");
  const [statusBusy, setStatusBusy] = useState(false);
  const [favoriteBusy, setFavoriteBusy] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [offerPanelHeight, setOfferPanelHeight] = useState<number | null>(null);
  const offerPanelRef = useRef<HTMLDivElement | null>(null);
  const offerResizeRef = useRef<{ startY: number; startHeight: number; lastY: number; frame: number | null } | null>(null);
  const [expandedDescriptionId, setExpandedDescriptionId] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);
  const [archiveReason, setArchiveReason] = useState("");
  const [radarLabel, setRadarLabel] = useState<string | null>(null);
  const [toast, setToast] = useState<{ id: number; message: string; undo?: () => void } | null>(null);
  const [descriptions, setDescriptions] = useState<Record<string, string | null>>({});
  const baseJob = useMemo(() => [...jobs, ...hiddenJobs, ...favoriteJobs, ...appliedJobs].find((job) => job.id === selectedId) || null, [appliedJobs, favoriteJobs, hiddenJobs, jobs, selectedId]);
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

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const queryFilters = { ...filters };
    delete queryFilters.source;
    fetchJobs(selectedSkill ? { ...queryFilters, skill: selectedSkill } : queryFilters, controller.signal)
      .then((result) => setJobs(result))
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError("No se pudo conectar con Radar API. Inicia `radar-api` y vuelve a cargar.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [filters, selectedSkill]);

  useEffect(() => {
    if (!filtersOpen) return;
    const controller = new AbortController();
    setSkillsLoading(true);
    fetchSkillOverview(filters, controller.signal)
      .then((result) => setSkillOverview(result))
      .catch(() => {})
      .finally(() => setSkillsLoading(false));
    return () => controller.abort();
  }, [filtersOpen, filters, mode]);

  const portalJobs = useMemo(() => {
    const requestedPortal = filters.source?.toLowerCase();
    if (!requestedPortal) return jobs;
    return jobs.filter((job) => sourceName(job.url).toLowerCase().includes(requestedPortal));
  }, [filters.source, jobs]);
  const portalCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const job of jobs) {
      const portal = sourceName(job.url).toLowerCase();
      counts[portal] = (counts[portal] || 0) + 1;
    }
    return counts;
  }, [jobs]);
  const mappedCount = portalJobs.filter((job) => job.latitude !== null && job.longitude !== null).length;
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
    [mode, portalJobs, radarCenter, radarRadiusKm, selectedDistrictKey],
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
    filters: activeView === "applications" ? (applicationsContext ? { status: applicationsContext.status } : undefined) : Object.fromEntries(Object.entries(filters).filter(([, value]) => Boolean(value))),
    selectedJob: selectedJob ? { id: selectedJob.id, title: selectedJob.title, company: selectedJob.company || undefined, district: selectedJob.district || undefined } : undefined,
    visibleCount: activeView === "applications" ? applicationsContext?.count : visibleJobs.length,
    districtJobs: mode === "radar" ? undefined : browsedDistrict?.count,
    analysis: activeView === "analysis" ? analysisContext : undefined,
    cvStudio: activeView === "cvs" ? studioContext ?? undefined : undefined,
  }), [activeView, analysisContext, applicationsContext, studioContext, browsedDistrict, filters, mode, radarDistrict, radarRadiusKm, selectedJob, visibleJobs.length]);
  useEffect(() => { onAgentContextChange?.(agentContext); }, [agentContext, onAgentContextChange]);
  const radarRadiusCounts = useMemo(
    () => RADAR_RADII.map((radius) => ({ radius, count: radarDistrictKey ? portalJobs.filter((job) => job.latitude !== null && job.longitude !== null && distanceKm(radarCenter, { latitude: job.latitude, longitude: job.longitude }) <= radius).length : 0 })),
    [portalJobs, radarCenter, radarDistrictKey],
  );
  const radarCountsMap = useMemo(() => Object.fromEntries(radarRadiusCounts.map((item) => [item.radius, item.count])), [radarRadiusCounts]);
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
  const archivedJobs = useMemo(() => archiveReason ? hiddenJobs.filter((job) => job.user_reason === archiveReason) : hiddenJobs, [archiveReason, hiddenJobs]);
  const listedJobs = showHidden ? archivedJobs : showFavorites ? favoriteJobs : showApplied ? appliedJobs : visibleJobs;
  const signalJobs = listedJobs;
  const {
    items: pagedJobs, items2: pagedJobsMap, containerRef, containerRef2,
    spacerHeight, spacerHeight2, trimmed, trimmed2,
  } = useProgressiveList(listedJobs, selectedId);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast((current) => current?.id === toast.id ? null : current), 6000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
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
        void hideJob(current, "not_interested").then(() => { if (next) setSelectedId(next.id); });
      } else if (current && event.key === "r" && showHidden) {
        event.preventDefault();
        void restoreJob(current);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

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

  const selectJob = useCallback((job: Job) => {
    setSelectedId(job.id);
    setExpandedDescriptionId(null);
    setHideReasonFor(null);
    setHideReason("");
    if (mode === "heatmap") setSelectedDistrictKey(districtKey(job.district));
  }, [mode]);

  function selectDistrict(key: string) {
    setSelectedDistrictKey((current) => current === key ? null : key);
    setSelectedId(null);
  }

  async function switchView(view: "active" | "favorites" | "hidden" | "applied") {
    setStatusError(null);
    try {
      if (view === "hidden" && hiddenJobs.length === 0) setHiddenJobs(await fetchHiddenJobs());
      if (view === "favorites" && favoriteJobs.length === 0) setFavoriteJobs(await fetchFavoriteJobs());
      if (view === "applied") setAppliedJobs(await fetchAppliedJobs());
    } catch {
      setStatusError(view === "hidden" ? "No se pudieron cargar las ofertas ocultas." : view === "applied" ? "No se pudieron cargar las postulaciones." : "No se pudieron cargar los favoritos.");
      return;
    }
    setShowHidden(view === "hidden");
    setShowFavorites(view === "favorites");
    setShowApplied(view === "applied");
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
      setFavoriteJobs((current) => nextValue
        ? [{ ...job, is_favorite: true }, ...current.filter((item) => item.id !== job.id)]
        : current.filter((item) => item.id !== job.id));
      if (!nextValue && showFavorites) setSelectedId(null);
    } catch {
      setStatusError(nextValue ? "No se pudo guardar el favorito." : "No se pudo quitar el favorito.");
    } finally {
      setFavoriteBusy(false);
    }
  }, [showFavorites]);

  async function hideJob(target: Job, reason: string) {
    setStatusBusy(true);
    setStatusError(null);
    try {
      await updateJobStatus(target.id, "hidden", reason);
      setJobs((current) => current.filter((job) => job.id !== target.id));
      setHiddenJobs((current) => [{ ...target, user_status: "hidden", user_reason: reason }, ...current.filter((job) => job.id !== target.id)]);
      setHideReasonFor(null);
      setHideReason("");
      setSelectedId((current) => current === target.id ? null : current);
      notify(`[ok] oferta archivada · motivo=${REASON_LABELS[reason] || reason}`, () => void restoreJob(target));
    } catch {
      setStatusError("No se pudo ocultar la oferta.");
    } finally {
      setStatusBusy(false);
    }
  }

  async function hideSelectedJob() {
    if (!selectedJob || !hideReasonFor || !hideReason) return;
    await hideJob(selectedJob, hideReason);
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

  function locateMe() {
    if (!navigator.geolocation) { notify("[err] tu navegador no soporta geolocalización"); return; }
    navigator.geolocation.getCurrentPosition(
      (position) => pickRadarCenter({ longitude: position.coords.longitude, latitude: position.coords.latitude }, "MI UBICACIÓN"),
      () => notify("[err] no se pudo obtener tu ubicación"),
      { timeout: 8000 },
    );
  }

  function changeMode(nextMode: MapMode) {
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

  // En todas las vistas el riel (y el botón de Filtros) se asoma al acercar el mouse a una franja amplia del borde izquierdo
  // y se queda visible mientras el cursor siga cerca; se oculta con un pequeño retraso.
  useEffect(() => {
    let timer: number | undefined;
    const setPeek = (value: boolean) => {
      if (railPeekRef.current === value) return;
      railPeekRef.current = value;
      setRailPeek(value);
      document.documentElement.classList.toggle("radar-rail-peek", value);
    };
    // La franja sensible llega hasta debajo del último botón del riel y del AgentDock (agente y ajustes).
    const zoneBottom = () => (document.querySelector(".agent-dock")?.getBoundingClientRect().bottom ?? 290) + 48;
    function onMove(event: MouseEvent) {
      if (document.querySelector(".boot-screen")) return;  // durante el arranque no se asoma nada
      const inside = event.clientX <= (railPeekRef.current ? 180 : 120) && event.clientY >= 0 && event.clientY <= zoneBottom();
      if (inside) {
        window.clearTimeout(timer);
        timer = undefined;
        setPeek(true);
      } else if (railPeekRef.current && timer === undefined) {
        timer = window.setTimeout(() => { timer = undefined; setPeek(false); }, 500);
      }
    }
    window.addEventListener("mousemove", onMove, { passive: true });
    return () => { window.removeEventListener("mousemove", onMove); window.clearTimeout(timer); document.documentElement.classList.remove("radar-rail-peek"); };
  }, []);

  async function markApplied(jobId: string) {
    try {
      await updateApplication(jobId, "applied");
      setAppliedJobIds((current) => new Set(current).add(jobId));
      if (showApplied) setAppliedJobs(await fetchAppliedJobs());
    } catch {
      setStatusError("No se pudo registrar la postulación.");
    }
  }

  function selectView(view: RadarView) {
    setActiveView(view);
    setRadarCenterOpen(false);
    setSelectedId(null);
    if (view === "map") {
      changeMode(lastMapMode.current);
      return;
    }
    setSelectedDistrictKey(null);
    setFiltersOpen(false);
    changeMode(view);
  }

  // Filtros es una capa global: abrirla o cerrarla no cambia de vista ni pierde estado.
  const filtersAvailable = activeView === "map";

  function applyAnalysisFilter(column: AnalysisFilterColumn, value: string): boolean {
    const normalized = value.trim().toLowerCase();
    if (column === "area" && AREAS.includes(value)) updateFilter("area", value);
    else if (column === "skill") setSelectedSkill(value);
    else if (column === "seniority" && SENIORITY_VALUES[normalized]) updateFilter("seniority", SENIORITY_VALUES[normalized]);
    else if (column === "work_mode" && WORK_MODE_VALUES[normalized]) updateFilter("work_mode", WORK_MODE_VALUES[normalized]);
    else if (column === "district" && districtKey(value)) { setActiveView("map"); setFiltersOpen(false); changeMode("heatmap"); setSelectedDistrictKey(districtKey(value)); notify(`[ok] filtro ${column}=${value} · mostrando en el mapa`); return true; }
    else return false;
    setActiveView("map");
    setFiltersOpen(false);
    changeMode(lastMapMode.current);
    notify(`[ok] filtro ${column}=${value} · mostrando en el mapa`);
    return true;
  }

  useEffect(() => {
    function applyResize() {
      const resize = offerResizeRef.current;
      const panel = offerPanelRef.current;
      if (resize) resize.frame = null;
      if (!resize || !panel) return;
      const maxHeight = Math.max(180, window.innerHeight - 36);
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

  return (
    <main className="radar-shell">
      {booting && <BootScreen ready={!loading} onDone={() => setBooting(false)} />}
      <div className="crt-scanlines" aria-hidden="true" />
      <section className="workspace">
        {filtersAvailable && <button className={`edge-menu-toggle is-autohide ${railPeek ? "is-peek" : ""} ${filtersOpen ? "is-open" : ""}`} type="button" aria-expanded={filtersOpen} aria-controls="radar-controls-panel" onClick={() => setFiltersOpen((current) => !current)}>
          <span aria-hidden="true">{filtersOpen ? "×" : "☷"}</span>
          <small>{filtersOpen ? "Cerrar" : "Filtros"}</small>
        </button>}
        <nav className={`mode-rail is-autohide ${railPeek ? "is-peek" : ""}`} aria-label="Vistas">
          <button className={activeView === "map" ? "active" : ""} type="button" aria-label="Mapa" title="Mapa" onClick={() => selectView("map")}><span aria-hidden="true">◎</span></button>
          <button className={activeView === "analysis" ? "active" : ""} type="button" aria-label="Análisis" title="Análisis" onClick={() => selectView("analysis")}><span aria-hidden="true">▦</span></button>
          <button className={activeView === "cvs" ? "active" : ""} type="button" aria-label="CVs objetivo" title="CVs objetivo" onClick={() => selectView("cvs")}><span aria-hidden="true">☰</span></button>
          <button className={activeView === "applications" ? "active" : ""} type="button" aria-label="Postulaciones" title="Postulaciones" onClick={() => selectView("applications")}><span aria-hidden="true">✓</span></button>
        </nav>
        <aside id="radar-controls-panel" className={`sidebar tool-${activeView !== "map" ? "analysis" : filtersOpen ? "filters" : mode === "radar" ? "radar" : "districts"} ${activeView === "map" && (filtersOpen || mode === "radar") ? "is-open" : ""}`}>
          <div className="sidebar-heading">
            <div><p className="eyebrow">Control room / 01</p><h1>Market scan</h1></div>
            <span className="result-count" key={loading ? "loading" : mappedCount}>{loading ? "---" : `${mappedCount}`}</span>
          </div>
          <form className="search-box" onSubmit={submitSearch}><span>⌕</span><input value={draftSearch} onChange={(event) => setDraftSearch(event.target.value)} placeholder="..." /><button type="submit" aria-label="Buscar">↵</button></form>

          <div className="filter-section"><div className="section-label">Filtros activos <span>{Object.values(filters).filter(Boolean).length + (selectedSkill ? 1 : 0)}</span></div>
            <label>Relevancia<select value={filters.relevance_tier || ""} onChange={(event) => updateFilter("relevance_tier", event.target.value)}><option value="core">Core · foco industrial</option><option value="adjacent">Adyacente · BI, PMO, SST</option><option value="out_of_focus">Fuera de foco</option><option value="">Todas</option></select></label>
            <label>Área profesional<select value={filters.area} onChange={(event) => updateFilter("area", event.target.value)}>{AREAS.map((area) => <option key={area} value={area}>{area || `Todas las áreas · ${visibleJobs.length || 0}`}{area && ` · ${areaCounts[area] || 0}`}</option>)}</select></label>
            <div className="two-columns"><label>Seniority<select value={filters.seniority} onChange={(event) => updateFilter("seniority", event.target.value)}><option value="">Todos{visibleJobs.length ? ` · ${visibleJobs.length}` : ""}</option><option value="intern">Practicante · {seniorityCounts.Practicante || 0}</option><option value="junior">Junior · {seniorityCounts.Junior || 0}</option><option value="mid">Intermedio · {seniorityCounts.Intermedio || 0}</option><option value="senior">Senior · {seniorityCounts.Senior || 0}</option></select></label><label>Modalidad<select value={filters.work_mode} onChange={(event) => updateFilter("work_mode", event.target.value)}><option value="">Todas{visibleJobs.length ? ` · ${visibleJobs.length}` : ""}</option><option value="onsite">Presencial · {modalityCounts.Presencial || 0}</option><option value="hybrid">Híbrido · {modalityCounts.Híbrido || 0}</option><option value="remote">Remoto · {modalityCounts.Remoto || 0}</option></select></label></div>
            <div className="two-columns"><label>Salario mínimo<input type="number" min="0" placeholder="S/" value={filters.min_salary} onChange={(event) => updateFilter("min_salary", event.target.value)} /></label><label>Antigüedad<select value={filters.max_age_days} onChange={(event) => updateFilter("max_age_days", event.target.value)}><option value="7">7 días</option><option value="14">14 días</option><option value="30">30 días</option><option value="90">90 días</option></select></label></div>
            <div className="two-columns"><label>Portal<select value={filters.source || ""} onChange={(event) => updateFilter("source", event.target.value)}><option value="">Todos los portales · {jobs.length}</option><option value="indeed">Indeed · {portalCounts.indeed || 0}</option><option value="computrabajo">Computrabajo · {portalCounts.computrabajo || 0}</option><option value="linkedin">LinkedIn · {portalCounts.linkedin || 0}</option><option value="bumeran">Bumeran · {portalCounts.bumeran || 0}</option><option value="laborum">Laborum · {portalCounts.laborum || 0}</option><option value="empleos">Empleos Perú · {portalCounts.empleos || 0}</option></select></label><label>Competencia<select value={selectedSkill || ""} onChange={(event) => { setSelectedSkill(event.target.value || null); setSelectedId(null); }}><option value="">Todas las competencias</option>{skillsLoading && <option disabled>Cargando…</option>}{(skillOverview?.skills || []).map((skill) => <option key={skill.name} value={skill.name}>{skill.name} · {skill.job_count}</option>)}</select></label></div>
          </div>

          <div className="map-mode"><div className="section-label">Visualización</div><div className="segmented">{([["jobs", "Ofertas"], ["heatmap", "Distritos"], ["radar", "Radar"]] as const).map(([value, label]) => <button key={value} className={mode === value ? "active" : ""} onClick={() => changeMode(value)} type="button">{label}</button>)}</div>{mode === "radar" && <div className="radar-controls"><div className="radar-center-control"><span>Centro del radar</span><div className="radar-center-select"><button className={radarCenterOpen ? "open" : ""} type="button" aria-haspopup="listbox" aria-expanded={radarCenterOpen} onClick={() => setRadarCenterOpen((current) => !current)}>{radarDistrict ? `${radarDistrict.district} · ${radarDistrict.count} ofertas` : "Selecciona un distrito"}<b>⌄</b></button>{radarCenterOpen && <div className="radar-center-menu" role="listbox" aria-label="Centro del radar">{districtStats.map((district) => <button key={district.key} className={radarDistrictKey === district.key ? "active" : ""} type="button" role="option" aria-selected={radarDistrictKey === district.key} onClick={() => selectRadarDistrict(district.key)}>{district.district}<span>{district.count} ofertas</span></button>)}</div>}</div></div><div className="radar-locate-row"><button className="radar-locate" type="button" onClick={locateMe}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M12 2v4M12 18v4M2 12h4M18 12h4" /></svg>usar mi ubicación</button><small>o haz clic en el mapa</small></div><span className="radar-readout">CENTER // {radarLabel || radarDistrict?.district || "LIMA"} · RANGE // {radarRadiusKm} KM · {visibleJobs.length} MATCHES</span><div className="radar-radius">{radarRadiusCounts.map(({ radius, count }) => <button key={radius} className={radarRadiusKm === radius ? "active" : ""} type="button" onClick={() => { setRadarRadiusKm(radius); setSelectedId(null); }}><strong>{radius} KM</strong><span>{count} ofertas</span></button>)}</div></div>}</div>
          <div className="job-list-header"><span>{showHidden ? "Ofertas ocultas" : showFavorites ? "Favoritos" : showApplied ? "Postuladas" : selectedSkill ? `Ofertas con ${selectedSkill}` : selectedDistrict ? `Ofertas en ${selectedDistrict.district}` : "Ofertas recientes"}</span><div className="job-list-tools"><span>{loading && !showHidden && !showFavorites && !showApplied ? "…" : `${showHidden ? archivedJobs.length : showFavorites ? favoriteJobs.length : showApplied ? appliedJobs.length : visibleJobs.filter((job) => job.latitude !== null && job.longitude !== null).length} ${showHidden ? "archivadas" : showFavorites ? "guardadas" : showApplied ? "postuladas" : "en mapa"}`}</span>{selectedSkill && !showHidden && !showFavorites && !showApplied && <button className="clear-skill-filter" type="button" onClick={() => setSelectedSkill(null)} aria-label="Quitar filtro de competencia" title="Quitar filtro de competencia">×</button>}</div></div>
          <div className="view-tabs" role="tablist" aria-label="Vista de ofertas">{([["active", "activas", !showHidden && !showFavorites && !showApplied], ["favorites", "★ fav", showFavorites], ["applied", "✓ postulé", showApplied], ["hidden", "archivo", showHidden]] as const).map(([view, label, active]) => <button key={view} type="button" role="tab" aria-selected={active} className={`view-tab ${view} ${active ? "active" : ""}`} onClick={() => void switchView(view)}>{view === "hidden" && <IconEyeOff />}{label}</button>)}</div>
          {showHidden && <div className="archive-filters" aria-label="Filtrar archivo por motivo">{ARCHIVE_FILTERS.map(([value, label]) => <button key={value} type="button" className={archiveReason === value ? "active" : ""} onClick={() => setArchiveReason(value)}>{label}</button>)}</div>}
          {statusError && <div className="status-error">{statusError}</div>}
          <div className="job-list" ref={containerRef}>{loading && !showHidden && !showFavorites && !showApplied && <div className="empty-state">Buscando ofertas<LoadingDots /></div>}{!loading && error && !showHidden && !showFavorites && !showApplied && <div className="empty-state error-state">{error}</div>}{!loading && !error && listedJobs.length === 0 && <div className="empty-state">{showHidden ? "> archivo vacío" : showFavorites ? "> sin favoritos guardados" : showApplied ? "> aún no registras postulaciones" : "No hay ofertas con estos filtros."}</div>}{trimmed && <div style={{ height: spacerHeight }} aria-hidden="true" />}{pagedJobs.map((job) => <JobCard key={job.id} job={job} selected={selectedId === job.id} showHidden={showHidden} onSelect={selectJob} onToggleFavorite={toggleFavorite} onQuickHide={(target) => void hideJob(target, "not_interested")} onRestore={(target) => void restoreJob(target)} />)}</div>
        </aside>

        <section className={`map-panel ${mode === "jobs" ? "reading-panel" : mode === "analysis" || mode === "cvs" || mode === "applications" ? "analysis-mode-panel" : ""}`}>
          {mode === "jobs" ? (
            <div className="job-reading-view">
              {selectedJob ? (
                <article className="reading-card">
                  <header className="reading-header">
                    <div className="reading-header-top">
                      <span className="reading-badge area">{selectedJob.primary_area || "General"}</span>
                      <span className="reading-badge date">{formatDate(selectedJob.published_at)}</span>
                      <button type="button" className={`reading-fav-btn ${selectedJob.is_favorite ? "active" : ""}`} aria-label={selectedJob.is_favorite ? "Quitar de favoritos (f)" : "Añadir a favoritos (f)"} title={selectedJob.is_favorite ? "Quitar de favoritos (f)" : "Añadir a favoritos (f)"} onClick={() => void toggleFavorite(selectedJob)}>
                        {selectedJob.is_favorite ? "★" : "☆"}
                      </button>
                    </div>
                    <h2 className="reading-title">{selectedJob.title}</h2>
                    <p className="reading-company">
                      {selectedJob.company || "Empresa no indicada"}
                      <CompanyMapsLink job={selectedJob} />
                    </p>
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
                      <button className="restore-button icon-only" type="button" aria-label="Restaurar oferta (r)" title="Restaurar oferta (r)" disabled={statusBusy} onClick={() => restoreJob(selectedJob)}><IconUndo /></button>
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
                      <button className="reading-hide-trigger icon-only" type="button" aria-label="Ocultar oferta (x)" title="Ocultar oferta (x)" onClick={() => { setHideReasonFor(selectedJob.id); setHideReason(""); }}><IconEyeOff /></button>
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
          ) : mode === "analysis" ? (
            <AnalysisView onApplyFilter={applyAnalysisFilter} onContextChange={setAnalysisContext} />
          ) : mode === "applications" ? (
            <ApplicationsView onContextChange={onApplicationsContext} />
          ) : mode === "cvs" ? (
            <CvView onStudioContext={setStudioContext} openJobId={studioJobId} onOpenJobConsumed={() => setStudioJobId(null)} />
          ) : (
            <>
              <div className="map-header">
                <div>
                  <p className="eyebrow">Geospatial intelligence / Lima</p>
                  <h2>{mode === "heatmap" && selectedDistrict ? selectedDistrict.district : mode === "heatmap" ? "Data analysis" : mode === "radar" ? `Signal lock${radarDistrict ? ` · ${radarDistrict.district}` : ""}` : "Lima Metropolitana"}</h2>
                </div>
                <div className="view-tabs map-view-toggle" role="tablist" aria-label="Tipo de mapa">{([["heatmap", "distritos"], ["radar", "radar"]] as const).map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={mode === value} className={`view-tab ${mode === value ? "active" : ""}`} onClick={() => changeMode(value)}>{label}</button>)}</div>
                <div className="map-legend">
                  {mode === "heatmap" ? <><span><i className="legend-scale low" /> Pocas ofertas</span><span><i className="legend-scale high" /> Más ofertas</span></> : <><span><i className="legend-dot" /> Oferta cercana</span><span><i className="legend-cluster" /> Concentración</span></>}
                  {mode === "radar" && <span><i className="legend-ring" /> Radio activo</span>}
                </div>
              </div>
              <div className={`map-wrap ${mode === "radar" ? "radar-active" : ""}`}>
                <MapView radarCounts={radarCountsMap} onPickRadarCenter={(center) => pickRadarCenter(center, "PUNTO EN MAPA")} jobs={visibleJobs} mode={mode} radarCenter={radarCenter} radarRadiusKm={radarRadiusKm} radarDistrictKey={radarDistrictKey} selectedDistrictKey={selectedDistrictKey} onSelectJob={(jobId) => { const job = visibleJobs.find((item) => item.id === jobId); if (job) selectJob(job); }} onSelectDistrict={selectDistrict} />
                {(mode === "heatmap" || mode === "radar") && <aside className="offer-scroll" aria-label="Ofertas visibles" style={offerPanelHeight ? { height: `${offerPanelHeight}px` } : undefined}><div className="offer-resize-handle" role="separator" aria-label="Ajustar altura de ofertas" onPointerDown={startOfferResize} /><div className="offer-scroll-heading"><span>SEÑALES // OFERTAS</span><div className="offer-scroll-tools"><strong>{signalJobs.length.toString().padStart(3, "0")}</strong><div className="view-tabs" role="tablist" aria-label="Vista de ofertas">{([["active", "activas", !showHidden && !showFavorites && !showApplied], ["favorites", "favoritos", showFavorites], ["applied", "postuladas", showApplied], ["hidden", "archivo", showHidden]] as const).map(([view, label, active]) => <button key={view} type="button" role="tab" aria-label={label} title={label} aria-selected={active} className={`view-tab ${view} ${active ? "active" : ""}`} onClick={() => void switchView(view)}><ViewIcon view={view} /></button>)}</div></div></div><div className="offer-scroll-list" ref={containerRef2}>{trimmed2 && <div style={{ height: spacerHeight2 }} aria-hidden="true" />}{pagedJobsMap.map((job) => <OfferSignalCard key={job.id} job={job} selected={selectedId === job.id} showHidden={showHidden} onSelect={selectJob} onToggleFavorite={toggleFavorite} onQuickHide={(target) => void hideJob(target, "not_interested")} onRestore={(target) => void restoreJob(target)} />)}{!loading && signalJobs.length === 0 && <span className="offer-scroll-empty">{showHidden ? "> archivo vacío" : showFavorites ? "> sin favoritos guardados" : showApplied ? "> aún no registras postulaciones" : "Selecciona un distrito para cargar señales"}</span>}</div></aside>}
                <div className="map-scan-label map-scan-label-top"><span className="scan-live-dot" />{mode === "radar" ? "RADAR LOCK" : mode === "heatmap" ? "DATA ANALYSIS" : "COLLECTING DATA"}<small>{"/// LIMA METROPOLITANA"}</small></div>
                <div className="map-scan-label map-scan-label-bottom"><span>COORD // 12°02&apos;46.0&quot;S 77°02&apos;35.0&quot;W</span><span>TRACKING // {visibleJobs.length.toString().padStart(3, "0")} SIGNALS</span></div>
                {mode === "heatmap" && districtStats.length > 0 && <aside className="district-map-overlay" aria-label="Distritos con ofertas"><div className="district-overlay-list"><button className={`district-row district-row-all ${selectedDistrictKey === null ? "selected" : ""}`} onClick={() => { setSelectedDistrictKey(null); setSelectedId(null); }} type="button"><span className="district-row-top"><strong>Todos</strong><span>{mappedCount}</span></span><span className="district-bar"><i style={{ width: "100%" }} /></span></button>{districtStats.map((district) => <button key={district.key} className={`district-row ${selectedDistrictKey === district.key ? "selected" : ""}`} onClick={() => selectDistrict(district.key)} type="button"><span className="district-row-top"><strong>{district.district}</strong><span>{district.count}</span></span><span className="district-bar"><i style={{ width: `${Math.max(10, (district.count / districtStats[0].count) * 100)}%` }} /></span></button>)}</div></aside>}
                {selectedJob && <article className={`job-popover ${expandedDescriptionId === selectedJob.id ? "is-description-expanded" : ""}`}>
                  {selectedJob.user_status !== "hidden" && <button className="hide-button popover-hide-button" type="button" aria-label="Ocultar oferta" title="Ocultar oferta" onClick={() => { setHideReasonFor(selectedJob.id); setHideReason(""); }}><IconEyeOff /></button>}
                  <button className="close-button" onClick={() => { setSelectedId(null); setExpandedDescriptionId(null); setHideReasonFor(null); setHideReason(""); }} aria-label="Cerrar detalle" type="button">×</button>
                  <button className="studio-link" type="button" onClick={() => { setStudioJobId(selectedJob.id); selectView("cvs"); }} title="Prepara tu CV para esta oferta en el Estudio">Estudio de CV →</button>
                  <button className="studio-link" type="button" disabled={appliedJobIds.has(selectedJob.id)} onClick={() => void markApplied(selectedJob.id)} title="Registra que ya postulaste en el portal (Radar no envía nada)">{appliedJobIds.has(selectedJob.id) ? "Postulación registrada ✓" : "Ya postulé"}</button>
                  <span className="job-area">{selectedJob.primary_area || "Sin área"}<span className="job-source"> · {sourceName(selectedJob.url)}</span></span>
                  <h3>{selectedJob.url ? <a className="job-popover-title" href={selectedJob.url} target="_blank" rel="noreferrer">{selectedJob.title}</a> : selectedJob.title}</h3>
                  <p className="popover-company">
                    {selectedJob.company || "Empresa no indicada"}
                    <CompanyMapsLink job={selectedJob} />
                  </p>
                  <div className="popover-divider" />
                  <div className="popover-grid">
                    <div><span>Ubicación</span><strong>{selectedJob.district || selectedJob.location || "Pendiente"}</strong></div>
                    <div><span>Modalidad</span><strong>{selectedJob.work_mode === "hybrid" ? "Híbrido" : selectedJob.work_mode === "remote" ? "Remoto" : selectedJob.work_mode === "onsite" ? "Presencial" : "No indicada"}</strong></div>
                    <div><span>Salario</span><strong>{formatSalary(selectedJob)}</strong></div>
                    <div><span>Publicado</span><strong>{formatDate(selectedJob.published_at)}</strong></div>
                  </div>
                  {selectedJob.description && <div className="popover-description-wrap"><div className="description-toggle" role="button" tabIndex={0} aria-label="Ver descripción completa" title="Ver descripción completa" aria-expanded={expandedDescriptionId === selectedJob.id} onClick={() => setExpandedDescriptionId((current) => current === selectedJob.id ? null : selectedJob.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setExpandedDescriptionId((current) => current === selectedJob.id ? null : selectedJob.id); } }}><div className="popover-description">{renderMarkdown(selectedJob.description)}</div></div></div>}
                  <div className="popover-actions">
                    {selectedJob.user_status === "hidden" && <button className="restore-button icon-only" type="button" aria-label="Restaurar oferta (r)" title="Restaurar oferta (r)" disabled={statusBusy} onClick={() => restoreJob(selectedJob)}><IconUndo /></button>}
                  </div>
                </article>}
                {selectedJob && hideReasonFor === selectedJob.id && selectedJob.user_status !== "hidden" && <aside className="hide-reason-popover" aria-label="Motivo para ocultar oferta"><button className="hide-reason-close" type="button" aria-label="Cerrar ocultar oferta" onClick={() => { setHideReasonFor(null); setHideReason(""); }}>×</button><span className="job-area">Ocultar oferta</span><strong>¿Por qué no quieres verla?</strong><label>Motivo<select value={hideReason} onChange={(event) => setHideReason(event.target.value)}><option value="" disabled>Selecciona un motivo</option><option value="closed">Ya cerró</option><option value="not_interested">No me interesa</option><option value="applied">Ya postulé</option><option value="duplicate">Oferta duplicada</option><option value="other">Otro</option></select></label><button className="restore-button" type="button" disabled={statusBusy || !hideReason} onClick={() => hideSelectedJob()}>{statusBusy ? "Guardando…" : "Confirmar ocultar"}</button><button className="cancel-hide" type="button" onClick={() => { setHideReasonFor(null); setHideReason(""); }}>Cancelar</button></aside>}
              </div>
            </>
          )}
        </section>

      </section>
      {toast && <div className="terminal-toast" role="status"><span>{toast.message}</span>{toast.undo && <button type="button" onClick={() => toast.undo?.()}>[u] deshacer</button>}</div>}
    </main>
  );
}
