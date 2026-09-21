"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, type ConversationHit, type ConversationInfo } from "../../lib/mobile-api";

const ago = (iso: string) => {
  const then = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`).getTime();
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 1) return "ahora";
  if (minutes < 60) return `hace ${minutes} min`;
  if (minutes < 60 * 24) return `hace ${Math.round(minutes / 60)} h`;
  const days = Math.round(minutes / 1440);
  return days === 1 ? "ayer" : days < 30 ? `hace ${days} d` : new Date(then).toLocaleDateString("es-PE");
};

type Row = { id: string; title: string; updated_at: string; count?: number; snippet?: string };

/** Selector de conversaciones al estilo `/resume` de Claude Code: escribe para filtrar (título y contenido),
 *  ↑↓ elige, Enter abre y Esc cierra. */
export default function ResumePicker({ onOpen, onDelete, onClose }: { onOpen: (id: string) => Promise<void>; onDelete: (id: string) => Promise<void>; onClose: () => void }) {
  const [items, setItems] = useState<ConversationInfo[] | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ConversationHit[]>([]);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);  // Ctrl+D pide confirmar antes de borrar
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => { input.current?.focus(); api.conversations(50).then((r) => setItems(r.conversations)).catch(() => setError("No se pudo cargar el historial.")); }, []);
  useEffect(() => {
    const q = query.trim();
    if (q.length < 3) { setHits([]); return; }
    const timer = window.setTimeout(() => { api.searchConversations(q).then((r) => setHits(r.conversations)).catch(() => setHits([])); }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  const rows = useMemo<Row[]>(() => {
    const q = query.trim().toLowerCase();
    const byTitle: Row[] = (items ?? []).filter((c) => !q || c.title.toLowerCase().includes(q))
      .map((c) => ({ id: c.id, title: c.title, updated_at: c.updated_at, count: c.lines }));
    const byContent: Row[] = hits.map((h) => ({ id: h.id, title: h.title, updated_at: h.updated_at, count: h.messages, snippet: h.snippets[0] }));
    const merged = new Map<string, Row>();
    for (const row of [...byContent, ...byTitle]) merged.set(row.id, { ...merged.get(row.id), ...row, snippet: row.snippet ?? merged.get(row.id)?.snippet });
    return [...merged.values()].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }, [items, hits, query]);

  useEffect(() => { setIndex(0); }, [query]);
  useEffect(() => { list.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" }); }, [index]);

  const open = async (row?: Row) => {
    if (!row) return;
    try { await onOpen(row.id); onClose(); } catch { setError("No se pudo abrir esa conversación."); }
  };
  const remove = async (row: Row) => {
    try {
      await onDelete(row.id);
      setItems((prev) => (prev ?? []).filter((c) => c.id !== row.id));
      setHits((prev) => prev.filter((h) => h.id !== row.id));
      setIndex((i) => Math.max(0, i - 1));
    } catch { setError("No se pudo borrar esa conversación."); }
    setConfirmId(null);
  };
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (confirmId) {  // confirmación de borrado: Enter borra, cualquier otra tecla cancela
      event.preventDefault();
      const row = rows.find((r) => r.id === confirmId);
      if (event.key === "Enter" && row) void remove(row); else setConfirmId(null);
      return;
    }
    if (event.ctrlKey && event.key.toLowerCase() === "d") { if (rows[index]) { event.preventDefault(); setConfirmId(rows[index].id); } return; }
    if (event.key === "Escape") { event.preventDefault(); onClose(); }
    else if (event.key === "ArrowDown") { event.preventDefault(); setIndex((i) => Math.min(i + 1, Math.max(rows.length - 1, 0))); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setIndex((i) => Math.max(i - 1, 0)); }
    else if (event.key === "Enter") { event.preventDefault(); void open(rows[index]); }
  };

  return (
    <div className="cfg-picker rs-picker" role="dialog" aria-label="Reanudar una conversación" onKeyDown={onKeyDown}>
      <div className="cfg-picker-title">Reanudar conversación</div>
      <input ref={input} className="rs-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar por título o contenido…" aria-label="Buscar conversaciones" autoComplete="off" spellCheck={false} />
      {error && <div className="term-error">{error}</div>}
      <ul ref={list} className="rs-list" role="listbox" aria-label="Conversaciones">
        {items === null && !error && <li className="rs-empty">Cargando…</li>}
        {items !== null && rows.length === 0 && <li className="rs-empty">{query ? "Nada coincide." : "Aún no hay conversaciones guardadas."}</li>}
        {rows.map((row, i) => (
          <li key={row.id} role="option" aria-selected={i === index} className={i === index ? "on" : ""} onMouseEnter={() => setIndex(i)} onClick={() => void open(row)}>
            <span aria-hidden>{i === index ? "❯" : " "}</span>
            <div><span className="rs-title">{row.title}</span>{row.snippet && <small className="rs-snippet">{row.snippet}</small>}</div>
            <small className="rs-meta">{ago(row.updated_at)}{row.count ? ` · ${row.count} msgs` : ""}</small>
          </li>
        ))}
      </ul>
      {confirmId
        ? <div className="rs-confirm">¿Borrar «{rows.find((r) => r.id === confirmId)?.title}»? Enter confirma · cualquier otra tecla cancela</div>
        : <div className="cfg-picker-hint">escribe para filtrar · ↑↓ elegir · Enter abrir · Ctrl+D borrar · Esc cerrar</div>}
    </div>
  );
}
