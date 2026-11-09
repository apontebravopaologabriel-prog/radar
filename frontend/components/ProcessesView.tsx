"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import { fetchProcesses, STAGES, type ProcessInput, type ProcessItem } from "../lib/processes-api";
import ProcessForm from "./ProcessForm";
import "./processes.css";
const History = dynamic(() => import("./ApplicationsView"));

export default function ProcessesView({ onContextChange }: { onContextChange?: (count: number, status: string) => void }) {
  const [items, setItems] = useState<ProcessItem[] | null>(null);
  const [closed, setClosed] = useState(false);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<ProcessItem | ProcessInput | null>(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState(false);
  const load = useCallback(async () => { try { setItems(await fetchProcesses()); setError(""); } catch (reason) { setError(String(reason)); } }, []);
  useEffect(() => { void load(); const changed = () => { void load(); }; window.addEventListener("radar:jobs-changed", changed); return () => window.removeEventListener("radar:jobs-changed", changed); }, [load]);
  const shown = (items ?? []).filter((p) => (p.stage === "closed") === closed && `${p.title} ${p.company} ${p.notes ?? ""} ${p.next_step ?? ""}`.toLowerCase().includes(query.toLowerCase()));
  useEffect(() => { onContextChange?.(shown.length, closed ? "closed" : "active"); }, [shown.length, closed, onContextChange]);
  return <section className="processes-view" aria-label="Procesos">
    <header><h2>Procesos</h2><p>Cuando ya hubo respuesta: contactos, pruebas, entrevistas y ofertas.</p></header>
    <div className="process-actions"><input type="search" aria-label="Buscar procesos" placeholder="Puesto o empresa…" value={query} onChange={(e) => setQuery(e.target.value)} /><button type="button" onClick={() => setEditing({ company: "", title: "", stage: "contact" })}>Agregar proceso</button></div>
    <div className="process-tabs" role="tablist" aria-label="Estado de procesos">{[false, true].map((value) => <button key={String(value)} role="tab" aria-selected={closed === value} onClick={() => { setClosed(value); setEditing(null); }}>{value ? "Cerrados" : "Activos"} · {(items ?? []).filter((p) => (p.stage === "closed") === value).length}</button>)}</div>
    {editing && <ProcessForm key={"id" in editing ? editing.id : "new"} initial={editing} id={"id" in editing ? editing.id : undefined} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); void load(); }} />}
    {error && <p role="alert">{error} <button onClick={() => void load()}>Reintentar</button></p>}
    {!items && !error && <p>Cargando procesos…</p>}
    {items && !shown.length && <p>{query ? "Sin coincidencias." : closed ? "No hay procesos cerrados." : "Sin procesos activos. No necesitas registrar cada solicitud: añade uno cuando te contacten."}</p>}
    <ul className="process-list">{shown.map((item) => <li key={item.id}><button type="button" className="process-row" onClick={() => setEditing(item)}><strong>{item.title}</strong><span>{item.company} · {STAGES[item.stage ?? "contact"]}</span>{(item.next_step || item.due_date) && <small>{item.next_step}{item.due_date ? ` · ${item.due_date.split("-").reverse().join("/")}` : ""}</small>}</button>{item.url && <a href={item.url} target="_blank" rel="noreferrer">Abrir enlace ↗</a>}</li>)}</ul>
    <details onToggle={(e) => setHistory(e.currentTarget.open)}><summary>Historial de postulaciones</summary>{history && <History />}</details>
  </section>;
}
