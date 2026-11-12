"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import { fetchAnalysisOffers, fetchOverview, scopeParams, type AnalysisOffers, type AnalysisScope, type AnalysisSelection, type Breakdown, type Overview } from "../lib/analysis-api";
import { fetchJob, fetchJobDescription } from "../lib/api";
import type { Job } from "../types";
import { MapJobPopover } from "./radar/JobDetailViews";
import type { AgentContext } from "../lib/mobile-api";
import "./analysis.css";

const SqlView = dynamic(() => import("./AnalysisSqlView"), { loading: () => <p role="status">Cargando editor…</p> });
const CompareView = dynamic(() => import("./CvInsights"), { loading: () => <p role="status">Cargando comparación…</p> });
const number = (n: number) => n.toLocaleString("es-PE", { maximumFractionDigits: 0 });
const LABELS: Record<string, string> = { intern: "Intern", trainee: "Trainee", junior: "Junior", mid: "Semi-Senior", senior: "Senior", senior_or_lead: "Senior / líder", lead: "Líder", manager: "Gerencia", unknown: "No indicado", onsite: "Presencial", hybrid: "Híbrido", remote: "Remoto", English: "Inglés", "Inventory Management": "Gestión de inventarios", Optimization: "Optimización", linkedin: "Linkedin", indeed: "Indeed", LinkedIn: "Linkedin", "JobSpy/LinkedIn": "Linkedin", "JobSpy/Indeed": "Indeed" };
const PERIODS: Record<string, string> = { month: "mes", monthly: "mes", year: "año", yearly: "año", annual: "año", hour: "hora", hourly: "hora", week: "semana", weekly: "semana", day: "día", daily: "día", fortnight: "quincena", unknown: "periodo no indicado" };
type Question = { key: AnalysisSelection["dimension"]; title: string; definition: string; rows: Breakdown[] };
const SKILL_GROUPS = { technical: "Herramientas y tecnologías", knowledge: "Conocimientos y métodos", language: "Idiomas", soft: "Habilidades blandas", other: "Otras" } as const;
const UNKNOWN_DISTRICT = "Sin distrito";
const RANKING_PREVIEW_ROWS = 8;
type ChartGroup = { key: string; label: string; rows: Breakdown[] };
const SENIORITY_ORDER = new Map(["intern", "trainee", "junior", "mid", "senior", "senior_or_lead", "lead", "manager", "unknown"].map((key, index) => [key, index]));
type SavedView = { name: string; scope: AnalysisScope };

function RankedBars({ rows, onSelect, limit = RANKING_PREVIEW_ROWS, selectedValue, offerTotal }: { rows: Breakdown[]; onSelect: (row: Breakdown) => void; limit?: number; selectedValue?: string; offerTotal?: number }) {
  const max = offerTotal || Math.max(...rows.map((row) => row.count), 1);
  return <div className="analysis-ranked">{rows.slice(0, limit).map((row) => <button key={row.value} className="analysis-rank" aria-pressed={row.value === selectedValue} onClick={() => onSelect(row)} title={`${LABELS[row.value] || row.value}: ${row.count} ofertas. Ver ofertas.`}>
    <span className="analysis-rank-label">{LABELS[row.value] || row.value}</span><strong>{number(row.count)}{offerTotal ? ` · ${number(row.count / offerTotal * 100)} %` : ""}</strong>
    <span className="analysis-rank-track" aria-hidden="true"><i style={{ width: `${row.count / max * 100}%` }} /></span>
  </button>)}{rows.length === 0 && <p className="analysis-muted">Sin datos en esta selección.</p>}</div>;
}

function GroupPicker({ rows, groups, value, onChange }: { rows: Breakdown[]; groups?: ChartGroup[]; value: string; onChange: (row?: Breakdown) => void }) {
  const disclosure = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const [search, setSearch] = useState("");
  const selected = rows.find((row) => row.value === value);
  const query = search.trim().toLocaleLowerCase("es");
  const matches = (groups?.length ? groups : [{ key: "all", label: "", rows }]).flatMap((group) => {
    const found = group.rows.filter((row) => `${LABELS[row.value] || row.value} ${row.value}`.toLocaleLowerCase("es").includes(query));
    return found.length ? [{ ...group, rows: found }] : [];
  });
  function close() {
    if (disclosure.current) disclosure.current.open = false;
    setSearch("");
    summary.current?.focus({ preventScroll: true });
  }
  return <details className="analysis-group-picker" ref={disclosure} onKeyDown={(event) => {
    if (event.key === "Escape" && disclosure.current?.open) { event.stopPropagation(); close(); }
  }}>
    <summary ref={summary}>{selected ? `${LABELS[selected.value] || selected.value} · ${number(selected.count)}` : "Todas las ofertas"}</summary>
    <div className="analysis-group-menu" aria-label="Grupo del gráfico">
      {rows.length > 8 && <input aria-label="Buscar grupo" type="search" placeholder="Buscar grupo…" value={search} onChange={(event) => setSearch(event.target.value)} />}
      <div className="analysis-group-options">
        <button type="button" aria-pressed={!value} onClick={() => { onChange(); close(); }}>Todas las ofertas</button>
        {matches.map((group) => <div key={group.key}>
          {group.label && <p className="analysis-group-label">{group.label}</p>}
          {group.rows.map((row) => <button type="button" key={row.value} aria-pressed={row.value === value}
            onClick={() => { onChange(row); close(); }}><span>{LABELS[row.value] || row.value}</span><span>{number(row.count)}</span></button>)}
        </div>)}
        {matches.length === 0 && <p className="analysis-muted">Sin coincidencias.</p>}
      </div>
    </div>
  </details>;
}

function SalaryColumns({ rows, onSelect }: { rows: Breakdown[]; onSelect: (row: Breakdown) => void }) {
  const max = Math.max(...rows.map((row) => row.count), 1);
  return <div className="analysis-salary-columns">{rows.map((row) =>
    <button type="button" key={row.value} disabled={!row.count} onClick={() => onSelect(row)} aria-label={`${row.value}: ${row.count} ofertas`}>
      <span className="analysis-salary-column" aria-hidden="true"><i style={{ height: `${row.count / max * 100}%` }} /><strong>{number(row.count)}</strong></span>
      <span>{row.value}</span>
    </button>
  )}</div>;
}

function PublicationLine({ rows, selectedValue, onSelect }: { rows: Breakdown[]; selectedValue?: string; onSelect: (row: Breakdown) => void }) {
  const max = Math.max(...rows.map((row) => row.count), 1);
  const points = rows.map((row) => 92 - 84 * row.count / max);
  return <div className="analysis-timeline">
    {points.slice(1).map((end, index) => {
      const start = points[index];
      return <i key={rows[index].value} aria-hidden="true" className="analysis-line-segment" style={{
        left: `${(index + .5) / rows.length * 100}%`,
        width: `${100 / rows.length}%`,
        clipPath: `polygon(0 calc(${start}% - 1px), 100% calc(${end}% - 1px), 100% calc(${end}% + 1px), 0 calc(${start}% + 1px))`,
      }} />;
    })}
    {rows.map((row, index) => <button type="button" key={row.value} title={`${row.value} · ${number(row.count)} ofertas`}
      aria-label={`${row.value}: ${number(row.count)} ofertas`} aria-pressed={selectedValue === row.value} onClick={() => onSelect(row)}>
      <span aria-hidden="true" style={{ top: `${points[index]}%` }} />
    </button>)}
  </div>;
}

const OTHER_TOOLS = "Otras herramientas";
const MODE_SHADES = ["#dedede", "#b6b6b6", "#909090", "#686868", "#494949"];

function CompositionDonut({ rows, selectedValue, onSelect, showShare = false }: { rows: Breakdown[]; selectedValue?: string; onSelect: (row: Breakdown) => void; showShare?: boolean }) {
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  if (!total) return <p className="analysis-muted">Sin datos en esta selección.</p>;
  let offset = 0;
  const stops = rows.map((row, index) => {
    const start = offset;
    offset += row.count;
    return `${MODE_SHADES[index % MODE_SHADES.length]} ${start / total * 100}% ${offset / total * 100}%`;
  });
  return <div className="analysis-modality">
    <div className="analysis-donut" style={{ background: `conic-gradient(${stops.join(", ")})` }} aria-hidden="true"><span>{number(total)}</span></div>
    <div className="analysis-modality-legend">{rows.map((row, index) => <button type="button" key={row.value}
      aria-pressed={selectedValue === row.value} disabled={row.value === OTHER_TOOLS} onClick={() => onSelect(row)}>
      <i aria-hidden="true" style={{ background: MODE_SHADES[index % MODE_SHADES.length] }} />
      <span>{LABELS[row.value] || row.value}</span><strong>{showShare ? `${number(row.count / total * 100)} %` : number(row.count)}</strong>
    </button>)}</div>
  </div>;
}

export default function AnalysisView({ scope, scopeLabels, resetRevision, onDetailOpenChange, onRestoreScope, onApplyChartFilter, onContextChange }: {
  scope: AnalysisScope; scopeLabels: string[]; resetRevision: number; onDetailOpenChange: (open: boolean) => void;
  onRestoreScope: (scope: AnalysisScope) => void; onApplyChartFilter: (key: "skill" | "work_mode", value: string) => void; onContextChange?: (context: AgentContext["analysis"]) => void;
}) {
  const [tab, setTab] = useState<"overview" | "compare" | "sql">("overview");
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [selection, setSelection] = useState<AnalysisSelection | null>(null);
  const [question, setQuestion] = useState<Question["key"] | null>(null);
  const [offers, setOffers] = useState<AnalysisOffers | null>(null);
  const [openedJob, setOpenedJob] = useState<{ id: string; preview?: Job } | null>(null);
  const [jobDetail, setJobDetail] = useState<Job | null>(null);
  const [jobError, setJobError] = useState("");
  const [expandedDescriptionId, setExpandedDescriptionId] = useState<string | null>(null);
  const jobLayer = useRef<HTMLDivElement>(null);
  const jobTrigger = useRef<HTMLElement | null>(null);
  const [offersError, setOffersError] = useState("");
  const resultsRef = useRef<HTMLDivElement>(null);
  const moreOffersRef = useRef<HTMLDivElement>(null);
  const retryOffers = useRef<(() => void) | null>(null);
  const trayHeight = useRef<number | null>(null);
  const resizeStart = useRef<{ y: number; height: number } | null>(null);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [viewName, setViewName] = useState("");
  const [storageError, setStorageError] = useState("");
  const detailRef = useRef<HTMLElement | null>(null);
  const detailTrigger = useRef<HTMLElement | null>(null);
  const [loadedScope, setLoadedScope] = useState("");
  const scopeKey = scopeParams(scope).toString();
  const currentData = loadedScope === scopeKey ? data : null;
  useEffect(() => {
    if (tab !== "overview") return;
    const request = new AbortController();
    setOpenedJob(null); setError(""); setQuestion(null); setSelection(null); setOffers(null);
    fetchOverview(scopeKey, request.signal).then((next) => { if (!request.signal.aborted) { setData(next); setLoadedScope(scopeKey); } })
      .catch((reason) => { if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : "No se pudo cargar el análisis."); });
    return () => request.abort();
  }, [scopeKey, retry, tab]);
  useEffect(() => {
    setQuestion(null);
    setSelection(null);
    setOpenedJob(null);
  }, [resetRevision]);
  const detailOpen = Boolean(question || openedJob);
  useEffect(() => { onDetailOpenChange(detailOpen); }, [detailOpen, onDetailOpenChange]);
  useEffect(() => () => onDetailOpenChange(false), [onDetailOpenChange]);
  useEffect(() => {
    try { const saved: SavedView[] = JSON.parse(localStorage.getItem("radar.analysis.scopes.v1") || "[]"); setSavedViews(saved.filter((v) => typeof v.name === "string" && typeof v.scope?.market_id === "string")); }
    catch { /* Storage is optional. */ }
  }, []);
  useEffect(() => {
    const root = resultsRef.current;
    if (!question || !root) return;
    const request = new AbortController();
    const seen = new Set<string>();
    let offset = 0;
    let pending = false;
    let done = false;

    setOffers(null);
    setOffersError("");
    root.scrollTop = 0;

    async function loadMore() {
      if (request.signal.aborted || pending || done) return;
      pending = true;
      setOffersError("");
      try {
        const next = await fetchAnalysisOffers(scopeKey, selection, offset, request.signal);
        if (request.signal.aborted) return;
        offset += next.jobs.length;
        done = !next.jobs.length || offset >= next.total;
        const jobs = next.jobs.filter((job) => {
          if (seen.has(job.id)) return false;
          seen.add(job.id);
          return true;
        });
        setOffers((current) => ({ ...next, jobs: [...(current?.jobs ?? []), ...jobs] }));
      } catch (reason) {
        if (!request.signal.aborted) setOffersError(reason instanceof Error ? reason.message : "No se pudieron cargar las ofertas.");
      } finally {
        pending = false;
      }
    }

    retryOffers.current = loadMore;
    void loadMore();
    return () => {
      request.abort();
      retryOffers.current = null;
    };
  }, [scopeKey, question, selection]);
  useEffect(() => {
    const root = resultsRef.current;
    const sentinel = moreOffersRef.current;
    if (!question || !root || !sentinel || !offers || offersError || offers.jobs.length >= offers.total) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) retryOffers.current?.();
    }, { root, rootMargin: "0px 0px 120px 0px" });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [question, offers, offersError]);
  useEffect(() => {
    if (!openedJob) return;
    const request = new AbortController();
    const loadJob = openedJob.preview ? Promise.resolve(openedJob.preview) : fetchJob(openedJob.id, request.signal);
    Promise.all([loadJob, fetchJobDescription(openedJob.id, request.signal)]).then(([job, description]) => {
      if (request.signal.aborted) return;
      if (!job) throw Error("No se encontró la oferta.");
      setJobDetail({ ...job, description });
    }).catch((reason) => {
      if (!request.signal.aborted) setJobError(reason instanceof Error ? reason.message : "No se pudo cargar la oferta.");
    });
    return () => request.abort();
  }, [openedJob]);
  useEffect(() => {
    if (openedJob) jobLayer.current?.focus({ preventScroll: true });
  }, [openedJob]);

  function setTrayHeight(height: number) {
    if (!detailRef.current) return;
    detailRef.current.style.setProperty("--analysis-tray-height", `${height}px`);
    trayHeight.current = detailRef.current.getBoundingClientRect().height;
  }

  function startResize(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0 || !detailRef.current) return;
    resizeStart.current = { y: event.clientY, height: detailRef.current.getBoundingClientRect().height };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function openJob(id: string, preview?: Job) {
    if (document.activeElement instanceof HTMLElement) jobTrigger.current = document.activeElement;
    setJobError("");
    setJobDetail(null);
    setExpandedDescriptionId(null);
    setOpenedJob({ id, preview });
  }

  function closeJob(restoreFocus = true) {
    setOpenedJob(null);
    if (restoreFocus) jobTrigger.current?.focus({ preventScroll: true });
  }

  useEffect(() => {
    onContextChange?.({ ready: Boolean(currentData) && tab === "overview", updatedAt: new Date().toISOString(),
      windows: currentData && tab === "overview" ? [{ title: `Selección del mapa · ${scopeLabels.join(" · ")}`, sql: "", columns: ["ofertas", "empresas", "con_sueldo"], rows: [[currentData.total, currentData.employers, currentData.salary_count]], rowCount: 1 }] : [], recentQueries: [] });
  }, [currentData, onContextChange, scopeLabels, tab]);
  function choose(key: Question["key"], row?: Breakdown, value?: string) {
    if (document.activeElement instanceof HTMLElement) detailTrigger.current = document.activeElement;
    closeJob(false); setQuestion(key); setSelection(row ? { dimension: key, value: value ?? row.value, label: LABELS[row.value] || row.value } : null);
    requestAnimationFrame(() => { detailRef.current?.focus({ preventScroll: true }); });
  }
  function closeDetail() {
    closeJob(false);
    setQuestion(null);
    setSelection(null);
    detailTrigger.current?.focus({ preventScroll: true });
  }

  const chartFilter = selection?.dimension === "skill" ? "skill"
    : selection?.dimension === "work_mode" && ["onsite", "hybrid", "remote"].includes(selection.value) ? "work_mode" : null;
  const skillGroups = Object.entries(SKILL_GROUPS).flatMap(([key, label]) => {
    const rows = currentData?.skill_groups?.[key] ?? [];
    return rows.length ? [{ key, label, rows }] : [];
  });
  const tools = skillGroups.find((group) => group.key === "technical");
  const toolSlices = tools?.rows.slice(0, 4) ?? [];
  const otherMentions = tools?.rows.slice(4).reduce((sum, row) => sum + row.count, 0) ?? 0;
  if (otherMentions) toolSlices.push({ value: OTHER_TOOLS, count: otherMentions });
  const unknownDistrict = currentData?.districts.find((row) => row.value === UNKNOWN_DISTRICT);
  const salaries = currentData?.salaries ?? [];
  const salaryLabel = (group: Overview["salaries"][number]) => `${group.currency === "unknown" ? "Moneda no indicada" : group.currency} · ${PERIODS[group.period] || group.period}`;
  const questions: Question[] = currentData ? [
    { key: "area", title: "Áreas con más ofertas", definition: "Una oferta se cuenta en su área principal del mercado seleccionado.", rows: currentData.areas },
    { key: "skill", title: "Competencias solicitadas", definition: "Ofertas que mencionan cada competencia del mercado seleccionado. Una oferta puede mencionar varias; no mide tu nivel personal.", rows: currentData.skills },
    { key: "company", title: "Empresas que publican", definition: "Solo empresas identificadas. Las ofertas confidenciales siguen en el total de ofertas.", rows: currentData.companies },
    { key: "district", title: "Dónde se concentran", definition: "Ofertas por distrito inferido. Las ubicaciones son aproximadas; no representan una dirección exacta.", rows: currentData.districts },
    { key: "seniority", title: "Nivel de experiencia", definition: "Nivel detectado en las ofertas; lo no especificado se conserva como tal.", rows: [...currentData.seniorities].sort((a, b) => (SENIORITY_ORDER.get(a.value) ?? SENIORITY_ORDER.size) - (SENIORITY_ORDER.get(b.value) ?? SENIORITY_ORDER.size)) },
    { key: "work_mode", title: "Modalidad de trabajo", definition: "Modalidad publicada o detectada; no se infiere una modalidad cuando falta evidencia.", rows: currentData.work_modes },
    { key: "source", title: "Portales en esta muestra", definition: "Ofertas encontradas por portal. Una oferta puede tener varias fuentes. Estos conteos describen la captura local, no la cuota del mercado laboral.", rows: currentData.sources },
  ] : [];
  const activeQuestion = questions.find((q) => q.key === question);
  function saveViews(views: SavedView[]) {
    setSavedViews(views); setStorageError("");
    try { localStorage.setItem("radar.analysis.scopes.v1", JSON.stringify(views)); } catch { setStorageError("No se pudo guardar la vista en este navegador."); }
  }
  const displayedJob = jobDetail ?? (openedJob?.preview ? { ...openedJob.preview, description: null } : null);
  return <>
  <div className="analysis-view">
    <header className="analysis-header"><div><p className="analysis-eyebrow">MERCADO LABORAL</p><h1>Análisis</h1></div><nav aria-label="Modo de análisis"><button aria-pressed={tab === "overview"} onClick={() => { if (tab !== "overview") closeJob(false); setTab("overview"); }}>Panel</button><button aria-pressed={tab === "compare"} onClick={() => { closeJob(false); setQuestion(null); setSelection(null); setTab("compare"); }}>Comparar</button><button aria-pressed={tab === "sql"} onClick={() => { closeJob(false); setQuestion(null); setSelection(null); setTab("sql"); }}>Consultas</button></nav></header>
    {tab === "sql" ? <SqlView /> : tab === "compare" ? <div className="analysis-compare"><CompareView onOpenJob={openJob} /></div> : <>
      <div className="analysis-scope"><span className="analysis-muted">Misma selección del mapa</span><p>{scopeLabels.join(" · ")}</p></div>
      <details className="analysis-saved"><summary>Vistas guardadas{savedViews.length ? ` · ${savedViews.length}` : ""}</summary><p className="analysis-muted">Guarda los filtros; el periodo se calcula de nuevo al abrir la vista.</p><form className="analysis-actions" onSubmit={(e) => { e.preventDefault(); if (viewName.trim()) { saveViews([...savedViews.filter((v) => v.name !== viewName.trim()), { name: viewName.trim(), scope }]); setViewName(""); } }}><input aria-label="Nombre de la vista" placeholder="Nombre de la vista" value={viewName} maxLength={80} onChange={(e) => setViewName(e.target.value)} /><button disabled={!viewName.trim() || !currentData}>Guardar vista</button></form><ul className="analysis-saved-list">{savedViews.map((v) => <li key={v.name}><button onClick={() => onRestoreScope(v.scope)}>{v.name}</button><button aria-label={`Eliminar vista ${v.name}`} onClick={() => saveViews(savedViews.filter((item) => item.name !== v.name))}>×</button></li>)}</ul>{storageError && <p role="alert">{storageError}</p>}</details>
      {error ? <div role="alert" className="analysis-message"><p>{error}</p><button onClick={() => setRetry((v) => v + 1)}>Reintentar</button></div> : !currentData ? <p role="status" className="analysis-message">Cargando análisis de esta selección…</p> : <>
        <div className="analysis-kpis"><button onClick={() => choose("area")}><strong>{number(currentData.total)}</strong><span>Ofertas en la selección</span></button><button onClick={() => choose("company")}><strong>{number(currentData.employers)}</strong><span>Empresas identificadas</span></button><div><strong>{Math.round(currentData.salary_share * 100)}<small>%</small></strong><span>Publican sueldo · {number(currentData.salary_count)} de {number(currentData.total)}</span></div></div>
        {scope.empty ? <p className="analysis-message">Elige un centro en Radar para analizar las ofertas dentro del radio.</p> : currentData.total === 0 ? <p className="analysis-message">No hay ofertas con esta selección. Amplía el periodo o cambia los filtros.</p> : <>
          <div className="analysis-grid">{questions.slice(0, 2).map((q) => <section className="analysis-chart" key={q.key}><button className="analysis-question" onClick={() => choose(q.key)}><h2>{q.key === "skill" ? "Herramientas y tecnologías" : q.title}</h2><span>Explorar ↗</span></button>
            {q.key === "skill" ? (
              tools ? <RankedBars rows={tools.rows} offerTotal={currentData.total} selectedValue={selection?.dimension === "skill" ? selection.value : undefined} onSelect={(row) => choose("skill", row)} />
                : <p className="analysis-muted">Sin herramientas detectadas en esta selección.</p>
            ) : <RankedBars rows={q.rows} selectedValue={selection?.dimension === q.key ? selection.value : undefined} onSelect={(row) => choose(q.key, row)} />}
            {q.key === "area" && <p className="analysis-definition">{number(currentData.total)} ofertas · área principal</p>}</section>)}
          <section className="analysis-chart analysis-wide"><button className="analysis-question" onClick={() => choose("publication")}><h2>Publicaciones por día</h2><span>Explorar ↗</span></button>
            <PublicationLine rows={currentData.publications} selectedValue={selection?.dimension === "publication" ? selection.value : undefined} onSelect={(day) => choose("publication", day)} />
            <div className="analysis-axis"><span>{currentData.start_date}</span><span>{currentData.end_date}</span></div><p className="analysis-definition">Fecha de publicación en Lima · ofertas de esta selección, no crecimiento del mercado ni capturas</p>
          </section>
          <section className="analysis-chart analysis-wide"><h2>Sueldos publicados</h2>
            {salaries.length > 0 ? <>
              <div className="analysis-salary-groups">{salaries.map((group) => <div key={`${group.currency}:${group.period}`}>
                <h3>{salaryLabel(group)}</h3>
                <p className="analysis-muted">Mediana {number(group.median)} · {number(group.count)} {group.count === 1 ? "oferta" : "ofertas"}</p>
                <SalaryColumns rows={group.bins} onSelect={(row) => choose("salary", { ...row, value: `${salaryLabel(group)} · ${row.value}` }, JSON.stringify([group.currency, group.period, row.value]))} />
              </div>)}</div>
              <p className="analysis-definition">Ofertas por tramo salarial. Cada rango se representa por su punto medio. Monedas y periodos se muestran por separado.</p>
            </> : <p className="analysis-muted">No hay sueldos comparables en esta selección.</p>}
          </section>
          {questions.slice(2).map((q) => <section className="analysis-chart" key={q.key}><button className="analysis-question" onClick={() => choose(q.key)}><h2>{q.title}</h2><span>Explorar ↗</span></button>
            {q.key === "work_mode" ? <CompositionDonut rows={q.rows} selectedValue={selection?.dimension === q.key ? selection.value : undefined} onSelect={(row) => choose(q.key, row)} /> :
              <RankedBars rows={q.key === "district" ? q.rows.filter((row) => row.value !== UNKNOWN_DISTRICT) : q.rows}
                selectedValue={selection?.dimension === q.key ? selection.value : undefined} onSelect={(row) => choose(q.key, row)} />}
            {q.key === "district" && unknownDistrict && <button className="analysis-coverage" type="button" onClick={() => choose("district", unknownDistrict)}>
              {number(unknownDistrict.count)} {unknownDistrict.count === 1 ? "oferta" : "ofertas"} sin distrito identificado
            </button>}
            <p className="analysis-definition">{q.definition}</p></section>)}</div>
        </>}
        {question && <section className="analysis-detail" ref={detailRef} tabIndex={-1}
          style={trayHeight.current === null ? undefined : { "--analysis-tray-height": `${trayHeight.current}px` } as React.CSSProperties} aria-label="Detalle del análisis" onKeyDown={(event) => {
          if (event.key === "Escape") { event.stopPropagation(); closeDetail(); }
        }}>
          <div className="offer-resize-handle" role="separator" aria-orientation="horizontal" aria-label="Ajustar altura de ofertas" tabIndex={0}
            onPointerDown={startResize} onPointerMove={(event) => {
              if (resizeStart.current && event.currentTarget.hasPointerCapture(event.pointerId)) {
                setTrayHeight(resizeStart.current.height + resizeStart.current.y - event.clientY);
              }
            }} onLostPointerCapture={() => { resizeStart.current = null; }}
            onKeyDown={(event) => {
              if ((event.key === "ArrowUp" || event.key === "ArrowDown") && detailRef.current) {
                event.preventDefault();
                setTrayHeight(detailRef.current.getBoundingClientRect().height + (event.key === "ArrowUp" ? 32 : -32));
              }
            }} />
          <div className="analysis-detail-heading">
            <h2>{activeQuestion?.title || (question === "salary" ? "Sueldos publicados" : "Publicaciones por día")}</h2>
            <span>{offers ? number(offers.total) : ""}</span>
            <button type="button" aria-label="Cerrar detalle" title="Cerrar detalle" onClick={closeDetail}>×</button>
          </div>
          {activeQuestion ? <GroupPicker key={activeQuestion.key} rows={activeQuestion.rows} groups={activeQuestion.key === "skill" ? skillGroups : undefined} value={selection?.value ?? ""} onChange={(row) => {
            closeJob(false);
            setSelection(row ? { dimension: activeQuestion.key, value: row.value, label: LABELS[row.value] || row.value } : null);
          }} /> : selection && <p className="analysis-muted">{selection.label}</p>}
          {chartFilter && selection && scope[chartFilter] !== selection.value &&
            <button className="analysis-detail-apply" onClick={() => {
              closeJob(false);
              onApplyChartFilter(chartFilter, selection.value);
              setQuestion(null);
              document.querySelector<HTMLButtonElement>('.edge-menu-toggle[aria-controls="radar-controls-panel"]')?.focus({ preventScroll: true });
            }}>Aplicar filtro al panel y al mapa</button>}
          <div className="analysis-detail-results" ref={resultsRef}>
            {question === "skill" && toolSlices.length > 0 && <details className="analysis-tool-composition">
              <summary>Distribución de menciones de herramientas</summary>
              <CompositionDonut rows={toolSlices} showShare selectedValue={selection?.value} onSelect={(row) => {
                closeJob(false);
                setSelection({ dimension: "skill", value: row.value, label: LABELS[row.value] || row.value });
              }} />
            </details>}
            {!offers ? !offersError && <p role="status">Cargando ofertas…</p> : offers.total === 0 ? <p>No hay ofertas en este grupo.</p> :
              <ul className="analysis-offers">{offers.jobs.map((job) => <li key={job.id}><button onClick={() => openJob(job.id, job)}><strong>{job.title}</strong><span>{job.company || "Empresa no indicada"} · {job.district || job.location || "Ubicación no indicada"}</span></button></li>)}</ul>}
            {offersError && <p role="alert">{offersError} <button type="button" onClick={() => retryOffers.current?.()}>Reintentar</button></p>}
            <div ref={moreOffersRef} className="analysis-more-offers" aria-hidden="true" />
          </div>
        </section>}
      </>}
    </>}
  </div>
  {openedJob && <div className={`analysis-job-layer${question ? " has-offer-tray" : ""}`} ref={jobLayer} tabIndex={-1}
    onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); closeJob(); } }}>
    {displayedJob && <MapJobPopover selectedJob={displayedJob} expandedDescriptionId={expandedDescriptionId}
      onToggleDescription={(id) => setExpandedDescriptionId((current) => current === id ? null : id)}
      onClose={() => closeJob()} />}
    {(!jobDetail || jobError) && <div className="analysis-job-feedback" role={jobError ? "alert" : "status"}>
      <span>{jobError || "Cargando descripción…"}</span>
      {!displayedJob && <button type="button" aria-label="Cerrar detalle" onClick={() => closeJob()}>×</button>}
    </div>}
  </div>}
  </>;
}
