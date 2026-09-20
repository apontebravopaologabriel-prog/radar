"use client";

import { PointerEvent as ReactPointerEvent, useCallback, useEffect, useRef, useState } from "react";
import { runAnalyticsQuery } from "../lib/api";
import type { AnalyticsQueryResult } from "../types";

type AnalysisWindow = {
  id: string;
  title: string;
  sql: string;
  result: AnalyticsQueryResult;
  x: number;
  y: number;
  z: number;
  width?: number;
  height?: number;
};

type LogEntry = { id: string; sql: string; status: "ok" | "error"; message: string };

type Preset = { label: string; sql: string };

const PRESETS: Preset[] = [
  { label: "Ofertas por área", sql: "SELECT ia.name AS area, COUNT(*) AS ofertas\nFROM jobs j\nLEFT JOIN job_areas ja ON ja.job_id = j.id AND ja.is_primary = 1\nLEFT JOIN industrial_areas ia ON ia.id = ja.area_id\nWHERE j.is_active = 1\nGROUP BY ia.name\nORDER BY ofertas DESC" },
  { label: "Total activas", sql: "SELECT COUNT(*) AS total_activas\nFROM jobs\nWHERE is_active = 1" },
  { label: "Mix de seniority", sql: "SELECT CASE seniority\n    WHEN 'intern' THEN 'Practicante' WHEN 'junior' THEN 'Junior'\n    WHEN 'mid' THEN 'Intermedio' WHEN 'senior' THEN 'Senior'\n    ELSE 'No indicado' END AS seniority,\n  COUNT(*) AS ofertas\nFROM jobs\nWHERE is_active = 1\nGROUP BY seniority\nORDER BY ofertas DESC" },
  { label: "Modalidad", sql: "SELECT work_mode, COUNT(*) AS ofertas\nFROM jobs\nWHERE is_active = 1\nGROUP BY work_mode\nORDER BY ofertas DESC" },
  { label: "Top empresas", sql: "SELECT c.name AS empresa, COUNT(*) AS ofertas\nFROM jobs j\nJOIN companies c ON c.id = j.company_id\nWHERE j.is_active = 1\nGROUP BY c.name\nORDER BY ofertas DESC\nLIMIT 10" },
  { label: "Salario por seniority", sql: "SELECT COALESCE(seniority, 'no indicado') AS seniority,\n  ROUND(AVG((salary_min + salary_max) / 2.0)) AS salario_promedio\nFROM jobs\nWHERE is_active = 1 AND salary_min IS NOT NULL\nGROUP BY seniority\nORDER BY salario_promedio DESC" },
  { label: "Tendencia semanal", sql: "SELECT strftime('%Y-W%W', published_at) AS semana, COUNT(*) AS ofertas\nFROM jobs\nWHERE is_active = 1 AND published_at IS NOT NULL\nGROUP BY semana\nORDER BY semana" },
  { label: "Rango salarial por seniority", sql: "SELECT COALESCE(seniority, 'no indicado') AS seniority,\n  ROUND(AVG(salary_min)) AS salario_min,\n  ROUND(AVG(salary_max)) AS salario_max\nFROM jobs\nWHERE is_active = 1 AND salary_min IS NOT NULL\nGROUP BY seniority\nORDER BY salario_min DESC" },
  { label: "Top skills demandadas", sql: "SELECT s.name AS skill, COUNT(*) AS ofertas\nFROM job_skills js\nJOIN skills s ON s.id = js.skill_id\nGROUP BY s.name\nORDER BY ofertas DESC\nLIMIT 15" },
  { label: "Skills por área", sql: "SELECT ia.name AS area, s.name AS skill, COUNT(*) AS menciones\nFROM job_skills js\nJOIN skills s ON s.id = js.skill_id\nJOIN job_areas ja ON ja.job_id = js.job_id AND ja.is_primary = 1\nJOIN industrial_areas ia ON ia.id = ja.area_id\nGROUP BY ia.name, s.name\nORDER BY menciones DESC\nLIMIT 15" },
  { label: "Evolución de una skill", sql: "-- cambia 'Python' por la skill que quieras seguir\nSELECT snapshot_date, metric_value AS menciones\nFROM market_snapshots\nWHERE metric_name = 'skill_jobs'\n  AND json_extract(dimensions, '$.skill') = 'Python'\nORDER BY snapshot_date ASC" },
  { label: "Brecha de competencias", sql: "SELECT s.name AS skill,\n  COUNT(js.job_id) AS demanda,\n  COALESCE(us.level, 'ninguno') AS tu_nivel\nFROM skills s\nLEFT JOIN job_skills js ON js.skill_id = s.id\nLEFT JOIN user_skills us ON us.skill_id = s.id\nGROUP BY s.name, us.level\nORDER BY demanda DESC\nLIMIT 15" },
  { label: "Salario por skill", sql: "SELECT s.name AS skill,\n  ROUND(AVG((j.salary_min + j.salary_max) / 2.0)) AS salario_promedio\nFROM job_skills js\nJOIN skills s ON s.id = js.skill_id\nJOIN jobs j ON j.id = js.job_id\nWHERE j.is_active = 1 AND j.salary_min IS NOT NULL\nGROUP BY s.name\nORDER BY salario_promedio DESC\nLIMIT 12" },
  { label: "Ofertas por sector", sql: "SELECT COALESCE(sector, 'sin sector') AS sector, COUNT(*) AS ofertas\nFROM jobs\nWHERE is_active = 1\nGROUP BY sector\nORDER BY ofertas DESC" },
  { label: "Ofertas por relevancia", sql: "SELECT relevance_tier, COUNT(*) AS ofertas\nFROM jobs\nWHERE is_active = 1\nGROUP BY relevance_tier\nORDER BY ofertas DESC" },
  { label: "Fuentes de las ofertas", sql: "SELECT src.name AS fuente, COUNT(DISTINCT j.id) AS ofertas\nFROM job_sources jsrc\nJOIN sources src ON src.id = jsrc.source_id\nJOIN jobs j ON j.id = jsrc.job_id\nWHERE j.is_active = 1\nGROUP BY src.name\nORDER BY ofertas DESC" },
  { label: "Ofertas nuevas (7 días)", sql: "SELECT COUNT(*) AS nuevas_7d\nFROM jobs\nWHERE is_active = 1 AND published_at >= date('now', '-7 days')" },
  { label: "Modalidad por área", sql: "SELECT ia.name AS area, j.work_mode, COUNT(*) AS ofertas\nFROM jobs j\nLEFT JOIN job_areas ja ON ja.job_id = j.id AND ja.is_primary = 1\nLEFT JOIN industrial_areas ia ON ia.id = ja.area_id\nWHERE j.is_active = 1\nGROUP BY ia.name, j.work_mode\nORDER BY ofertas DESC\nLIMIT 15" },
];

function isNumeric(value: unknown): value is number {
  return typeof value === "number";
}

function looksLikeDate(value: unknown): boolean {
  return typeof value === "string" && /^\d{4}(-\d{2}){0,2}/.test(value);
}

type ResultShape = "empty" | "stat" | "bars" | "grouped-bars" | "series" | "table";

function classifyResult(result: AnalyticsQueryResult): ResultShape {
  const { columns, rows } = result;
  if (rows.length === 0) return "empty";
  if (columns.length === 1 && rows.length === 1 && isNumeric(rows[0][0])) return "stat";
  if (columns.length === 2 && rows.every((row) => isNumeric(row[1]))) {
    return looksLikeDate(rows[0][0]) ? "series" : "bars";
  }
  if (columns.length === 3 && rows.every((row) => isNumeric(row[1]) && isNumeric(row[2]))) return "grouped-bars";
  return "table";
}

function formatCell(value: string | number | null): string {
  if (value === null) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString("es-PE") : value.toLocaleString("es-PE", { maximumFractionDigits: 2 });
  return value;
}

type FilterColumn = "area" | "skill" | "seniority" | "work_mode" | "district";
type ApplyFilter = (column: FilterColumn, value: string) => boolean;

const FILTER_COLUMNS: Record<string, FilterColumn> = { area: "area", skill: "skill", seniority: "seniority", work_mode: "work_mode", modalidad: "work_mode", distrito: "district", district: "district" };

// Si la columna es filtrable, el valor se vuelve un botón que lleva al mapa con ese filtro.
function FilterValue({ column, value, onApply }: { column: string; value: string | number | null; onApply?: ApplyFilter }) {
  const kind = FILTER_COLUMNS[column.trim().toLowerCase()];
  const text = formatCell(value);
  if (!onApply || !kind || typeof value !== "string" || !value) return <>{text}</>;
  return <button type="button" className="analysis-filter-link" title="Ver estas ofertas en el mapa" onClick={() => onApply(kind, value)}>{text}</button>;
}

function ResultView({ result, onApply }: { result: AnalyticsQueryResult; onApply?: ApplyFilter }) {
  const shape = classifyResult(result);
  if (shape === "empty") return <p className="analysis-empty-result">La consulta no devolvió filas.</p>;
  if (shape === "stat") {
    return (
      <div className="analysis-stat">
        <strong>{formatCell(result.rows[0][0])}</strong>
        <span>{result.columns[0]}</span>
      </div>
    );
  }
  if (shape === "bars") {
    const max = Math.max(...result.rows.map((row) => Number(row[1]) || 0), 1);
    return (
      <div className="analysis-bars">
        {result.rows.map((row, index) => (
          <div className="analysis-bar-row" key={index}>
            <span className="analysis-bar-label"><FilterValue column={result.columns[0]} value={row[0]} onApply={onApply} /></span>
            <span className="analysis-bar-track"><i style={{ width: `${Math.max(4, (Number(row[1]) / max) * 100)}%` }} /></span>
            <span className="analysis-bar-value">{formatCell(row[1])}</span>
          </div>
        ))}
      </div>
    );
  }
  if (shape === "grouped-bars") {
    const max = Math.max(...result.rows.flatMap((row) => [Number(row[1]) || 0, Number(row[2]) || 0]), 1);
    return (
      <div className="analysis-grouped-bars">
        <div className="analysis-grouped-legend"><span className="a">{result.columns[1]}</span><span className="b">{result.columns[2]}</span></div>
        {result.rows.map((row, index) => (
          <div className="analysis-grouped-row" key={index}>
            <span className="analysis-bar-label"><FilterValue column={result.columns[0]} value={row[0]} onApply={onApply} /></span>
            <div className="analysis-grouped-tracks">
              <span className="analysis-bar-track a"><i style={{ width: `${Math.max(4, (Number(row[1]) / max) * 100)}%` }} /></span>
              <span className="analysis-bar-track b"><i style={{ width: `${Math.max(4, (Number(row[2]) / max) * 100)}%` }} /></span>
            </div>
            <span className="analysis-bar-value">{formatCell(row[1])} / {formatCell(row[2])}</span>
          </div>
        ))}
      </div>
    );
  }
  if (shape === "series") {
    const max = Math.max(...result.rows.map((row) => Number(row[1]) || 0), 1);
    return (
      <div className="analysis-series">
        <div className="analysis-series-track">
          {result.rows.map((row, index) => (
            <i key={index} title={`${row[0]}: ${row[1]}`} style={{ height: `${Math.max(6, (Number(row[1]) / max) * 100)}%` }} />
          ))}
        </div>
        <div className="analysis-series-axis"><span>{formatCell(result.rows[0][0])}</span><span>{formatCell(result.rows[result.rows.length - 1][0])}</span></div>
      </div>
    );
  }
  return (
    <div className="analysis-table-wrap">
      <table className="analysis-table">
        <thead><tr>{result.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
        <tbody>{result.rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}><FilterValue column={result.columns[cellIndex]} value={cell} onApply={onApply} /></td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

type Box = { x: number; y: number; w: number; h: number };

const STORAGE_KEY = "radar.analysis.desktop.v1";
const GRAVITY = 2600;
const DEFAULT_WINDOW_WIDTH = 360;
const DEFAULT_WINDOW_HEIGHT = 260;

// Colocación estilo tetris: prueba varias columnas y elige donde la pieza cae más abajo.
function placeSkyline(existing: Box[], w: number, h: number, desktopWidth: number, floor: number): { x: number; restY: number } {
  const candidates = new Set<number>([16]);
  for (const box of existing) { candidates.add(box.x); candidates.add(box.x + box.w + 12); }
  let best = { x: 16, restY: -Infinity };
  for (const x of [...candidates].sort((a, b) => a - b)) {
    if (x < 0 || x + w > desktopWidth) continue;
    let top = floor;
    for (const box of existing) if (x < box.x + box.w && x + w > box.x) top = Math.min(top, box.y);
    if (top - h > best.restY) best = { x, restY: top - h };
  }
  return best;
}

function downloadCsv(result: AnalyticsQueryResult, name: string) {
  const quote = (value: string | number | null) => {
    const text = value === null ? "" : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const csv = [result.columns.map(quote).join(","), ...result.rows.map((row) => row.map(quote).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${name.replace(/[^\w-]+/g, "_").slice(0, 40) || "consulta"}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

type ResizeEdge = "e" | "s" | "se";
type ResizeState = { id: string; edge: ResizeEdge; startX: number; startY: number; startWidth: number; startHeight: number; width: number; height: number; el: HTMLDivElement };
const MIN_WINDOW_WIDTH = 220;
const MIN_WINDOW_HEIGHT = 120;

type DragState = { id: string; startClientX: number; startClientY: number; originX: number; originY: number; lastClientX: number; lastClientY: number; el: HTMLDivElement; frame: number | null };

export default function AnalysisView({ onApplyFilter }: { onApplyFilter?: ApplyFilter }) {
  const [windows, setWindows] = useState<AnalysisWindow[]>([]);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [sqlPinned, setSqlPinned] = useState(false);
  const [sqlHover, setSqlHover] = useState(false);
  const [sqlFocus, setSqlFocus] = useState(false);
  const sqlHoverRef = useRef(false);
  const [logOpen, setLogOpen] = useState(false);
  const gutterRef = useRef<HTMLDivElement | null>(null);
  const zCounterRef = useRef(1);
  const cascadeRef = useRef(0);
  const dragRef = useRef<DragState | null>(null);
  const resizeRef = useRef<ResizeState | null>(null);
  const [gravity, setGravity] = useState(false);
  const [kick, setKick] = useState(0);
  const windowsRef = useRef<AnalysisWindow[]>([]);
  const elsRef = useRef(new Map<string, HTMLDivElement>());
  const posRef = useRef(new Map<string, { x: number; y: number }>());
  const velocityRef = useRef(new Map<string, number>());
  const simFrameRef = useRef<number | null>(null);
  const hydratedRef = useRef(false);
  const logRef = useRef<HTMLDivElement | null>(null);
  const desktopRef = useRef<HTMLDivElement | null>(null);

  windowsRef.current = windows;

  // El editor se colapsa a su barra cuando está ocioso. Sigue abierto si está fijado, tiene el foco,
  // tiene texto sin ejecutar, hay una consulta en curso o el mouse está cerca de la esquina.
  const sqlOpen = sqlPinned || sqlHover || sqlFocus || busy || input.trim().length > 0;
  const sqlOpenRef = useRef(sqlOpen);
  sqlOpenRef.current = sqlOpen;

  useEffect(() => {
    let timer: number | undefined;
    const setHover = (value: boolean) => {
      if (sqlHoverRef.current === value) return;
      sqlHoverRef.current = value;
      setSqlHover(value);
    };
    function onMove(event: MouseEvent) {
      const rect = desktopRef.current?.getBoundingClientRect();
      if (!rect) return;
      const reachX = event.clientX >= rect.left && event.clientX <= rect.left + (sqlOpenRef.current ? 520 : 480);
      const reachY = event.clientY >= rect.bottom - (sqlOpenRef.current ? 300 : 110) && event.clientY <= rect.bottom;
      if (reachX && reachY) {
        window.clearTimeout(timer);
        timer = undefined;
        setHover(true);
      } else if (sqlHoverRef.current && timer === undefined) {
        timer = window.setTimeout(() => { timer = undefined; setHover(false); }, 600);
      }
    }
    window.addEventListener("mousemove", onMove, { passive: true });
    return () => { window.removeEventListener("mousemove", onMove); window.clearTimeout(timer); };
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [log]);

  const bringToFront = useCallback((id: string) => {
    zCounterRef.current += 1;
    setWindows((current) => current.map((win) => (win.id === id ? { ...win, z: zCounterRef.current } : win)));
  }, []);

  useEffect(() => {
    function onMove(event: PointerEvent) {
      const drag = dragRef.current;
      if (!drag) return;
      drag.lastClientX = event.clientX;
      drag.lastClientY = event.clientY;
      if (drag.frame !== null) return;
      drag.frame = requestAnimationFrame(() => {
        const current = dragRef.current;
        if (!current) return;
        current.frame = null;
        const nextX = current.originX + (current.lastClientX - current.startClientX);
        const nextY = current.originY + (current.lastClientY - current.startClientY);
        current.el.style.transform = `translate(${nextX}px, ${nextY}px)`;
        current.el.dataset.x = String(nextX);
        current.el.dataset.y = String(nextY);
      });
    }
    function onUp() {
      const drag = dragRef.current;
      if (drag) {
        if (drag.frame !== null) cancelAnimationFrame(drag.frame);
        const x = Number(drag.el.dataset.x ?? drag.originX);
        const y = Number(drag.el.dataset.y ?? drag.originY);
        setWindows((current) => current.map((win) => (win.id === drag.id ? { ...win, x, y } : win)));
        document.body.classList.remove("is-resizing");
      }
      dragRef.current = null;
    }
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerup", onUp, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, []);

  function startDrag(event: ReactPointerEvent<HTMLDivElement>, win: AnalysisWindow) {
    // Los botones de la cabecera (editar, cerrar) no inician arrastre: el arrastre
    // desactiva los eventos de puntero y el clic nunca llegaría al botón.
    if ((event.target as HTMLElement).closest("button")) return;
    const el = event.currentTarget.closest(".analysis-window") as HTMLDivElement | null;
    if (!el) return;
    event.preventDefault();
    bringToFront(win.id);
    document.body.classList.add("is-resizing");
    dragRef.current = { id: win.id, startClientX: event.clientX, startClientY: event.clientY, originX: Number(el.dataset.x ?? win.x), originY: Number(el.dataset.y ?? win.y), lastClientX: event.clientX, lastClientY: event.clientY, el, frame: null };
  }

  // Estirar usa captura de puntero en el asa: sigue funcionando aunque el cursor salga de la ventana.
  function startResize(event: ReactPointerEvent<HTMLDivElement>, win: AnalysisWindow, edge: ResizeEdge) {
    const el = event.currentTarget.closest(".analysis-window") as HTMLDivElement | null;
    if (!el) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    bringToFront(win.id);
    const rect = el.getBoundingClientRect();
    resizeRef.current = { id: win.id, edge, startX: event.clientX, startY: event.clientY, startWidth: rect.width, startHeight: rect.height, width: rect.width, height: rect.height, el };
  }

  function moveResize(event: ReactPointerEvent<HTMLDivElement>) {
    const resize = resizeRef.current;
    if (!resize) return;
    const desktop = desktopRef.current?.getBoundingClientRect();
    const maxWidth = desktop ? desktop.width : Infinity;
    const maxHeight = desktop ? desktop.height : Infinity;
    if (resize.edge !== "s") resize.width = Math.min(maxWidth, Math.max(MIN_WINDOW_WIDTH, resize.startWidth + event.clientX - resize.startX));
    if (resize.edge !== "e") resize.height = Math.min(maxHeight, Math.max(MIN_WINDOW_HEIGHT, resize.startHeight + event.clientY - resize.startY));
    resize.el.style.width = `${resize.width}px`;
    resize.el.style.height = `${resize.height}px`;
    resize.el.style.maxHeight = "none";
  }

  function endResize() {
    const resize = resizeRef.current;
    if (!resize) return;
    resizeRef.current = null;
    setWindows((current) => current.map((win) => (win.id === resize.id ? { ...win, width: resize.width, height: resize.height } : win)));
  }

  async function refreshWindow(id: string) {
    const target = windowsRef.current.find((win) => win.id === id);
    if (!target) return;
    try {
      const result = await runAnalyticsQuery(target.sql);
      setWindows((current) => current.map((win) => (win.id === id ? { ...win, result } : win)));
    } catch {
      /* se conserva el resultado anterior */
    }
  }

  function closeWindow(id: string) {
    setWindows((current) => current.filter((win) => win.id !== id));
  }

  function closeAllWindows() {
    setWindows([]);
  }

  // Física: cada ventana es un rectángulo sin rotación que cae hasta el suelo o hasta apoyarse en otra.
  const stepPhysics = useCallback((dt: number): boolean => {
    const desktop = desktopRef.current;
    if (!desktop) return false;
    const floor = desktop.clientHeight;
    const busyId = dragRef.current?.id ?? resizeRef.current?.id;
    const bodies = windowsRef.current.flatMap((win) => {
      const el = elsRef.current.get(win.id);
      if (!el) return [];
      const fixed = win.id === busyId;
      const pos = fixed ? { x: Number(el.dataset.x ?? win.x), y: Number(el.dataset.y ?? win.y) } : posRef.current.get(win.id) ?? { x: win.x, y: win.y };
      return [{ id: win.id, el, fixed, pos, w: el.offsetWidth, h: el.offsetHeight }];
    }).sort((a, b) => b.pos.y + b.h - (a.pos.y + a.h));
    const placed: typeof bodies = [];
    let moving = false;
    for (const body of bodies) {
      if (body.fixed) {
        posRef.current.set(body.id, body.pos);
        velocityRef.current.set(body.id, 0);
        placed.push(body);
        continue;
      }
      let vy = (velocityRef.current.get(body.id) ?? 0) + GRAVITY * dt;
      let y = body.pos.y + vy * dt;
      let rest = floor - body.h;
      for (const other of placed) {
        if (body.pos.x < other.pos.x + other.w && body.pos.x + body.w > other.pos.x) rest = Math.min(rest, other.pos.y - body.h);
      }
      if (y >= rest) {
        y = rest;
        vy = Math.abs(vy) > 320 ? -vy * 0.25 : 0;
      }
      if (Math.abs(y - body.pos.y) > 0.05 || vy !== 0) moving = true;
      body.pos = { x: body.pos.x, y };
      posRef.current.set(body.id, body.pos);
      velocityRef.current.set(body.id, vy);
      body.el.style.transform = `translate(${body.pos.x}px, ${y}px)`;
      body.el.dataset.x = String(body.pos.x);
      body.el.dataset.y = String(y);
      placed.push(body);
    }
    return moving;
  }, []);

  const commitPositions = useCallback(() => {
    setWindows((current) => {
      let changed = false;
      const next = current.map((win) => {
        const pos = posRef.current.get(win.id);
        if (!pos || (Math.abs(pos.x - win.x) <= 0.5 && Math.abs(pos.y - win.y) <= 0.5)) return win;
        changed = true;
        return { ...win, x: pos.x, y: pos.y };
      });
      // Sin cambios se devuelve el mismo arreglo: así el efecto de gravedad no se vuelve a disparar.
      return changed ? next : current;
    });
  }, []);

  const runPhysics = useCallback(() => {
    if (simFrameRef.current !== null) return;
    for (const win of windowsRef.current) {
      const pos = posRef.current.get(win.id);
      if (!pos || Math.abs(pos.x - win.x) > 0.5 || Math.abs(pos.y - win.y) > 0.5) {
        posRef.current.set(win.id, { x: win.x, y: win.y });
        velocityRef.current.set(win.id, 0);
      }
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      for (let index = 0; index < 900 && stepPhysics(1 / 30); index += 1);
      commitPositions();
      return;
    }
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.033, (now - last) / 1000);
      last = now;
      if (stepPhysics(dt)) {
        simFrameRef.current = requestAnimationFrame(tick);
      } else {
        simFrameRef.current = null;
        commitPositions();
      }
    };
    simFrameRef.current = requestAnimationFrame(tick);
  }, [commitPositions, stepPhysics]);

  useEffect(() => {
    if (gravity) runPhysics();
  }, [gravity, runPhysics, windows]);

  useEffect(() => {
    if (kick > 0) runPhysics();
  }, [kick, runPhysics]);

  useEffect(() => () => { if (simFrameRef.current !== null) cancelAnimationFrame(simFrameRef.current); }, []);

  // Escritorio persistente: se guardan las consultas y su disposición; los datos se piden de nuevo al abrir.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null") as { gravity?: boolean; windows?: Array<Omit<AnalysisWindow, "result">> } | null;
        if (saved?.gravity) setGravity(true);
        const restored = await Promise.all((saved?.windows || []).map(async (item) => {
          try { return { ...item, result: await runAnalyticsQuery(item.sql) } as AnalysisWindow; } catch { return null; }
        }));
        if (cancelled) return;
        const list = restored.filter((item): item is AnalysisWindow => item !== null);
        if (list.length > 0) {
          zCounterRef.current = Math.max(1, ...list.map((item) => item.z));
          setWindows(list);
        }
      } catch {
        /* sin almacenamiento disponible: el escritorio arranca vacío */
      } finally {
        if (!cancelled) hydratedRef.current = true;
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!hydratedRef.current) return;
    const timer = window.setTimeout(() => {
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ gravity, windows: windows.map(({ result: _result, ...rest }) => rest) }));
      } catch {
        /* almacenamiento lleno o bloqueado */
      }
    }, 400);
    return () => window.clearTimeout(timer);
  }, [gravity, windows]);

  function boxesOf(exclude?: string): Box[] {
    return windowsRef.current.filter((win) => win.id !== exclude).map((win) => {
      const el = elsRef.current.get(win.id);
      const pos = posRef.current.get(win.id) ?? { x: win.x, y: win.y };
      return { x: pos.x, y: pos.y, w: el?.offsetWidth ?? win.width ?? DEFAULT_WINDOW_WIDTH, h: el?.offsetHeight ?? win.height ?? DEFAULT_WINDOW_HEIGHT };
    });
  }

  // Cuadrícula: reparte las ventanas en el aire, sin física. Apaga la gravedad para que no vuelvan a caer.
  function gridWindows() {
    const desktop = desktopRef.current;
    if (!desktop || windowsRef.current.length === 0) return;
    setGravity(false);
    const rect = desktop.getBoundingClientRect();
    const margin = 16;
    const count = windowsRef.current.length;
    const cols = Math.max(1, Math.ceil(Math.sqrt(count)));
    const rows = Math.max(1, Math.ceil(count / cols));
    const cellW = Math.max(240, (rect.width - margin * (cols + 1)) / cols);
    const cellH = Math.max(180, (rect.height - margin * (rows + 1)) / rows);
    const layout = new Map<string, { x: number; y: number; width: number; height: number }>();
    windowsRef.current.forEach((win, index) => {
      const col = index % cols;
      const row = Math.floor(index / cols);
      layout.set(win.id, { x: margin + col * (cellW + margin), y: margin + row * (cellH + margin), width: cellW, height: cellH });
    });
    for (const [id, box] of layout) {
      posRef.current.set(id, { x: box.x, y: box.y });
      velocityRef.current.set(id, 0);
      const el = elsRef.current.get(id);
      if (el) { el.style.transform = `translate(${box.x}px, ${box.y}px)`; el.dataset.x = String(box.x); el.dataset.y = String(box.y); }
    }
    setWindows((current) => current.map((win) => ({ ...win, ...(layout.get(win.id) ?? {}) })));
  }

  function toggleGravity() {
    const next = !gravity;
    setGravity(next);
    if (next) organizeWindows();
  }

  // Tetris: las ventanas caen escalonadas desde arriba y se compactan como piezas de tetris.
  function organizeWindows() {
    const desktop = desktopRef.current;
    if (!desktop || windowsRef.current.length === 0) return;
    const placed: Box[] = [];
    const targets = new Map<string, { x: number; y: number }>();
    windowsRef.current.forEach((win, index) => {
      const el = elsRef.current.get(win.id);
      const w = el?.offsetWidth ?? DEFAULT_WINDOW_WIDTH;
      const h = el?.offsetHeight ?? DEFAULT_WINDOW_HEIGHT;
      const spot = placeSkyline(placed, w, h, desktop.clientWidth, desktop.clientHeight);
      placed.push({ x: spot.x, y: spot.restY, w, h });
      targets.set(win.id, { x: spot.x, y: -h - index * (h * 0.6 + 40) });
    });
    for (const [id, pos] of targets) {
      posRef.current.set(id, pos);
      velocityRef.current.set(id, 0);
      const el = elsRef.current.get(id);
      if (el) { el.style.transform = `translate(${pos.x}px, ${pos.y}px)`; el.dataset.x = String(pos.x); el.dataset.y = String(pos.y); }
    }
    setWindows((current) => current.map((win) => ({ ...win, ...(targets.get(win.id) ?? {}) })));
    setKick((current) => current + 1);
  }

  async function runQuery(sql: string) {
    const trimmed = sql.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      const result = await runAnalyticsQuery(trimmed);
      cascadeRef.current += 1;
      const offset = (cascadeRef.current % 6) * 26;
      zCounterRef.current += 1;
      const desktop = desktopRef.current;
      const spawnWidth = Math.min(DEFAULT_WINDOW_WIDTH, (desktop?.clientWidth ?? DEFAULT_WINDOW_WIDTH) - 24);
      // Con gravedad la ventana aparece sobre el escritorio y cae en la columna más baja.
      const spawn = gravity && desktop
        ? { x: placeSkyline(boxesOf(), spawnWidth, DEFAULT_WINDOW_HEIGHT, desktop.clientWidth, desktop.clientHeight).x, y: -DEFAULT_WINDOW_HEIGHT - 40 }
        : { x: 24 + offset, y: 24 + offset };
      setWindows((current) => [...current, {
        id: `win-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        title: trimmed.replace(/\s+/g, " ").slice(0, 56),
        sql: trimmed,
        result,
        x: spawn.x,
        y: spawn.y,
        z: zCounterRef.current,
      }]);
      setLog((current) => [...current.slice(-40), { id: `log-${Date.now()}`, sql: trimmed, status: "ok", message: `${result.row_count} fila${result.row_count === 1 ? "" : "s"} · ${result.elapsed_ms}ms${result.truncated ? " · truncado a 500" : ""}` }]);
      setInput("");
      setHistoryIndex(null);
    } catch (error) {
      setLog((current) => [...current.slice(-40), { id: `log-${Date.now()}`, sql: trimmed, status: "error", message: error instanceof Error ? error.message : "Error desconocido" }]);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runQuery(input);
  }

  function navigateHistory(direction: -1 | 1) {
    const executed = log.map((entry) => entry.sql);
    if (executed.length === 0) return;
    const nextIndex = historyIndex === null ? executed.length - 1 : Math.max(0, Math.min(executed.length - 1, historyIndex + direction));
    setHistoryIndex(nextIndex);
    setInput(executed[nextIndex]);
  }

  return (
    <div className="analysis-view">
      <div className="analysis-desktop" ref={desktopRef}>
        <div className="analysis-desktop-toolbar">
          <button type="button" className={gravity ? "active" : ""} onClick={toggleGravity} aria-pressed={gravity} aria-label="Modo tetris" title={gravity ? "Modo tetris activo: desactivar" : "Modo tetris: las ventanas caen y se apilan con física"}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="14" width="7" height="6" /><rect x="13" y="14" width="7" height="6" /><rect x="8" y="5" width="8" height="6" /></svg>
          </button>
          {windows.length > 0 && (
            <>
              <button type="button" onClick={gridWindows} aria-label="Ordenar en cuadrícula" title="Ordenar en cuadrícula (en el aire, sin física)">
                <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="7" height="7" /><rect x="13" y="4" width="7" height="7" /><rect x="4" y="13" width="7" height="7" /><rect x="13" y="13" width="7" height="7" /></svg>
              </button>
              <button type="button" onClick={closeAllWindows} aria-label="Cerrar todo" title={`Cerrar todo (${windows.length})`}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            </>
          )}
        </div>
        {windows.length === 0 && <div className="analysis-empty-desktop"><span className="eyebrow">Análisis</span></div>}
        {windows.map((win) => (
          <div
            key={win.id}
            className="analysis-window"
            ref={(el) => { if (el) elsRef.current.set(win.id, el); else elsRef.current.delete(win.id); }}
            style={{ transform: `translate(${win.x}px, ${win.y}px)`, zIndex: win.z, width: win.width ? `${win.width}px` : undefined, height: win.height ? `${win.height}px` : undefined, maxHeight: win.height ? "none" : undefined }}
            onPointerDown={() => bringToFront(win.id)}
          >
            <div className="analysis-window-header" onPointerDown={(event) => startDrag(event, win)}>
              <strong title={win.sql}>{win.title}</strong>
              <div className="analysis-window-tools">
                <button type="button" title="Actualizar datos" aria-label="Actualizar datos" onClick={(event) => { event.stopPropagation(); void refreshWindow(win.id); }}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v4h-4" /></svg></button>
                <button type="button" title="Descargar CSV" aria-label="Descargar CSV" onClick={(event) => { event.stopPropagation(); downloadCsv(win.result, win.title); }}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v10M8 10l4 4 4-4M5 19h14" /></svg></button>
                <button type="button" title="Editar consulta" aria-label="Editar consulta" onClick={(event) => { event.stopPropagation(); setInput(win.sql); }}>✎</button>
                <button type="button" title="Cerrar" aria-label="Cerrar dashboard" onClick={(event) => { event.stopPropagation(); closeWindow(win.id); }}>×</button>
              </div>
            </div>
            <div className="analysis-window-body">
              <ResultView result={win.result} onApply={onApplyFilter} />
            </div>
            {(["e", "s", "se"] as const).map((edge) => (
              <div key={edge} className={`analysis-resize ${edge}`} onPointerDown={(event) => startResize(event, win, edge)} onPointerMove={moveResize} onPointerUp={endResize} onPointerCancel={endResize} />
            ))}
          </div>
        ))}
      </div>

      <form className={`analysis-sql ${sqlOpen ? "" : "is-collapsed"}`} onSubmit={submit} onFocus={() => setSqlFocus(true)} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setSqlFocus(false); }}>
        <div className="analysis-sql-bar">
          <span className="analysis-sql-title">SQL</span>
          <select className="analysis-sql-presets" value="" aria-label="Presets de consulta" onChange={(event) => { const preset = PRESETS.find((item) => item.label === event.target.value); if (preset) setInput(preset.sql); }}>
            <option value="">presets…</option>
            {PRESETS.map((preset) => <option key={preset.label} value={preset.label}>{preset.label}</option>)}
          </select>
          <button type="submit" className="analysis-sql-run" disabled={busy || !input.trim()} title="Ejecutar (Enter)">{busy ? "…" : "▶ run"}</button>
          <button type="button" className={`analysis-sql-collapse ${sqlPinned ? "active" : ""}`} aria-pressed={sqlPinned} aria-label="Fijar editor abierto" title={sqlPinned ? "Fijado abierto: pulsa para autoocultar" : "Fijar abierto (si no, se oculta solo)"} onClick={() => setSqlPinned((current) => !current)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4h6l-1 6 3 3H7l3-3-1-6zM12 13v7" /></svg></button>
        </div>
        {sqlOpen && (
          <>
            <div className="analysis-sql-editor">
              <div className="analysis-sql-gutter" ref={gutterRef} aria-hidden="true">
                {Array.from({ length: Math.max(input.split("\n").length, 1) }, (_, index) => <span key={index}>{index + 1}</span>)}
              </div>
              <textarea
                value={input}
                wrap="off"
                onChange={(event) => setInput(event.target.value)}
                onScroll={(event) => { if (gutterRef.current) gutterRef.current.scrollTop = event.currentTarget.scrollTop; }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void runQuery(input);
                  } else if (event.key === "ArrowUp" && !input.includes("\n")) {
                    event.preventDefault();
                    navigateHistory(-1);
                  } else if (event.key === "ArrowDown" && !input.includes("\n")) {
                    event.preventDefault();
                    navigateHistory(1);
                  }
                }}
                placeholder="SELECT …"
                rows={6}
                spellCheck={false}
              />
            </div>
            <div className="analysis-sql-status">
              <button type="button" className="analysis-sql-log-toggle" onClick={() => setLogOpen((current) => !current)} aria-expanded={logOpen}>
                {log.length === 0 ? "sin consultas" : `${logOpen ? "▾" : "▸"} ${log[log.length - 1].status === "error" ? `error: ${log[log.length - 1].message}` : log[log.length - 1].message}`}
              </button>
              <span>↑↓ historial · ⇧↵ salto</span>
            </div>
            {logOpen && (
              <div className="analysis-terminal-log" ref={logRef}>
                {log.map((entry) => (
                  <div key={entry.id} className={`analysis-log-line ${entry.status}`}>
                    <span className="analysis-log-prompt">&gt;</span> <span className="analysis-log-sql">{entry.sql.replace(/\s+/g, " ")}</span>
                    <div className="analysis-log-status">{entry.status === "error" ? `ERROR: ${entry.message}` : entry.message}</div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </form>
    </div>
  );
}
