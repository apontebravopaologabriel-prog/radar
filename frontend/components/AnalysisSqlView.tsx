"use client";

import { useEffect, useRef, useState } from "react";
import { runAnalyticsQuery } from "../lib/api";
import type { AnalyticsQueryResult } from "../types";

type SavedQuery = { title: string; sql: string };
const KEY = "radar.analysis.queries.v2";

export default function AnalysisSqlView() {
  const [sql, setSql] = useState("SELECT COUNT(*) AS ofertas FROM jobs WHERE is_active = 1");
  const [saved, setSaved] = useState<SavedQuery[]>([]);
  const [title, setTitle] = useState("");
  const [result, setResult] = useState<AnalyticsQueryResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    try {
      const current = localStorage.getItem(KEY);
      const legacy = JSON.parse(localStorage.getItem("radar.analysis.desktop.v1") || "null");
      const queries: SavedQuery[] = current ? JSON.parse(current) : (legacy?.windows || []);
      setSaved(queries.filter((q) => typeof q.title === "string" && typeof q.sql === "string").map(({ title, sql }) => ({ title, sql })));
    } catch { /* Saved queries are optional. */ }
    return () => controller.current?.abort();
  }, []);
  async function run() {
    controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    setBusy(true); setError(""); setResult(null);
    try { const next = await runAnalyticsQuery(sql, request.signal); if (!request.signal.aborted) setResult(next); }
    catch (reason) { if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : "No se pudo ejecutar la consulta."); }
    finally { if (!request.signal.aborted) setBusy(false); }
  }
  function store(queries: SavedQuery[]) {
    setSaved(queries);
    try { localStorage.setItem(KEY, JSON.stringify(queries)); } catch { setError("No se pudo guardar la consulta en este navegador."); }
  }
  function csv() {
    if (!result) return;
    const quote = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;
    const text = [result.columns, ...result.rows].map((row) => row.map(quote).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a"); a.href = url; a.download = "consulta-radar.csv"; a.click(); URL.revokeObjectURL(url);
  }
  return <section className="analysis-sql-workspace" aria-label="Consultas de datos">
    <h2>Consultas de datos</h2>
    <p className="analysis-muted">Solo lectura. Estas consultas no usan los filtros del mapa y pueden incluir otros mercados, periodos y registros históricos.</p>
    <form onSubmit={(event) => { event.preventDefault(); void run(); }}>
      <label>Consulta SQL<textarea aria-label="Consulta SQL" spellCheck={false} value={sql} onChange={(e) => setSql(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void run(); } }} /></label>
      <div className="analysis-actions"><button disabled={busy || !sql.trim()}>{busy ? "Consultando…" : "Ejecutar"}</button><span className="analysis-muted">Ctrl + Enter</span></div>
    </form>
    <form className="analysis-actions" onSubmit={(e) => { e.preventDefault(); if (title.trim() && sql.trim()) { store([...saved.filter((q) => q.title !== title.trim()), { title: title.trim(), sql }]); setTitle(""); } }}>
      <input aria-label="Nombre de la consulta" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Nombre de la consulta" maxLength={80} />
      <button disabled={!title.trim() || !sql.trim()}>Guardar consulta</button>
    </form>
    {saved.length > 0 && <details><summary>Consultas guardadas · {saved.length}</summary><ul className="analysis-saved-list">{saved.map((query, i) => <li key={`${query.title}-${i}`}><button onClick={() => { setSql(query.sql); setResult(null); setError(""); }}>{query.title}</button><button aria-label={`Eliminar consulta ${query.title}`} onClick={() => store(saved.filter((_, index) => index !== i))}>×</button></li>)}</ul></details>}
    {error && <p role="alert">{error}</p>}
    {result && <><div className="analysis-actions"><p>{result.row_count} filas · {result.elapsed_ms.toFixed(0)} ms{result.truncated ? " · Resultado limitado" : ""}</p><button onClick={csv}>Descargar CSV</button></div><div className="analysis-table-wrap"><table><thead><tr>{result.columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead><tbody>{result.rows.map((row, i) => <tr key={i}>{row.map((cell, n) => <td key={n}>{cell === null ? "—" : String(cell)}</td>)}</tr>)}</tbody></table></div></>}
  </section>;
}
