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

function ResultView({ result }: { result: AnalyticsQueryResult }) {
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
            <span className="analysis-bar-label">{formatCell(row[0])}</span>
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
            <span className="analysis-bar-label">{formatCell(row[0])}</span>
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
        <tbody>{result.rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{formatCell(cell)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

type DragState = { id: string; startClientX: number; startClientY: number; originX: number; originY: number; lastClientX: number; lastClientY: number; el: HTMLDivElement; frame: number | null };

export default function AnalysisView() {
  const [windows, setWindows] = useState<AnalysisWindow[]>([]);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [presetsOpen, setPresetsOpen] = useState(false);
  const zCounterRef = useRef(1);
  const cascadeRef = useRef(0);
  const dragRef = useRef<DragState | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);
  const desktopRef = useRef<HTMLDivElement | null>(null);

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
    const el = event.currentTarget.closest(".analysis-window") as HTMLDivElement | null;
    if (!el) return;
    event.preventDefault();
    bringToFront(win.id);
    document.body.classList.add("is-resizing");
    dragRef.current = { id: win.id, startClientX: event.clientX, startClientY: event.clientY, originX: win.x, originY: win.y, lastClientX: event.clientX, lastClientY: event.clientY, el, frame: null };
  }

  function closeWindow(id: string) {
    setWindows((current) => current.filter((win) => win.id !== id));
  }

  function closeAllWindows() {
    setWindows([]);
  }

  function arrangeWindows() {
    const desktop = desktopRef.current;
    setWindows((current) => {
      if (!desktop || current.length === 0) return current;
      const rect = desktop.getBoundingClientRect();
      const margin = 16;
      const cols = Math.max(1, Math.ceil(Math.sqrt(current.length)));
      const rows = Math.max(1, Math.ceil(current.length / cols));
      const cellW = Math.max(240, (rect.width - margin * (cols + 1)) / cols);
      const cellH = Math.max(180, (rect.height - margin * (rows + 1)) / rows);
      return current.map((win, index) => {
        const col = index % cols;
        const row = Math.floor(index / cols);
        return { ...win, x: margin + col * (cellW + margin), y: margin + row * (cellH + margin), width: cellW, height: cellH };
      });
    });
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
      setWindows((current) => [...current, {
        id: `win-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        title: trimmed.replace(/\s+/g, " ").slice(0, 56),
        sql: trimmed,
        result,
        x: 24 + offset,
        y: 24 + offset,
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
        {windows.length > 0 && (
          <div className="analysis-desktop-toolbar">
            <span>{windows.length} dashboard{windows.length === 1 ? "" : "s"}</span>
            <button type="button" onClick={arrangeWindows} title="Organizar ventanas en cuadrícula">⊞ Organizar</button>
            <button type="button" onClick={closeAllWindows} title="Cerrar todos los dashboards">Cerrar todo</button>
          </div>
        )}
        {windows.length === 0 && <div className="analysis-empty-desktop"><span className="eyebrow">Análisis</span></div>}
        {windows.map((win) => (
          <div
            key={win.id}
            className="analysis-window"
            style={{ transform: `translate(${win.x}px, ${win.y}px)`, zIndex: win.z, width: win.width ? `${win.width}px` : undefined, height: win.height ? `${win.height}px` : undefined }}
            onPointerDown={() => bringToFront(win.id)}
          >
            <div className="analysis-window-header" onPointerDown={(event) => startDrag(event, win)}>
              <strong title={win.sql}>{win.title}</strong>
              <div className="analysis-window-tools">
                <button type="button" title="Editar consulta" aria-label="Editar consulta" onClick={(event) => { event.stopPropagation(); setInput(win.sql); }}>✎</button>
                <button type="button" title="Cerrar" aria-label="Cerrar dashboard" onClick={(event) => { event.stopPropagation(); closeWindow(win.id); }}>×</button>
              </div>
            </div>
            <div className="analysis-window-body">
              <ResultView result={win.result} />
            </div>
          </div>
        ))}
      </div>

      <div className="analysis-terminal">
        <div className={`analysis-presets-drawer ${presetsOpen ? "is-open" : ""}`}>
          <button type="button" className="analysis-presets-toggle" onClick={() => setPresetsOpen((current) => !current)} aria-expanded={presetsOpen}>
            <span>{presetsOpen ? "▾" : "▸"}</span> Presets
          </button>
          {presetsOpen && (
            <div className="analysis-presets-list">
              {PRESETS.map((preset) => (
                <button key={preset.label} type="button" className="analysis-preset-chip" onClick={() => { setInput(preset.sql); setPresetsOpen(false); }}>{preset.label}</button>
              ))}
            </div>
          )}
        </div>
        <div className="analysis-terminal-main">
          <div className="analysis-terminal-log" ref={logRef}>
            {log.map((entry) => (
              <div key={entry.id} className={`analysis-log-line ${entry.status}`}>
                <span className="analysis-log-prompt">&gt;</span> <span className="analysis-log-sql">{entry.sql.replace(/\s+/g, " ")}</span>
                <div className="analysis-log-status">{entry.status === "error" ? `ERROR: ${entry.message}` : entry.message}</div>
              </div>
            ))}
          </div>
          <form className="analysis-terminal-input-row" onSubmit={submit}>
            <span className="analysis-prompt">&gt;</span>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
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
              placeholder="SQL…"
              rows={4}
              spellCheck={false}
            />
            <button type="submit" disabled={busy || !input.trim()}>{busy ? "…" : "RUN"}</button>
          </form>
        </div>
      </div>
    </div>
  );
}
