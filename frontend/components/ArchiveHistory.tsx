"use client";

import { useEffect, useState } from "react";
import { fetchArchiveHistory } from "../lib/processes-api";
import { formatPublicationDate } from "../lib/tracking-dates";
import TrackingOfferDetail from "./TrackingOfferDetail";

type ArchivePage = Awaited<ReturnType<typeof fetchArchiveHistory>>;

export default function ArchiveHistory() {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<ArchivePage | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetchArchiveHistory(query.trim(), page, controller.signal).then((data) => {
        if (!controller.signal.aborted) setResult(data);
      }).catch((reason) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "No se pudo cargar el historial.");
      });
    }, query ? 180 : 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, page]);

  function changePage(next: number) {
    setResult(null);
    setError("");
    setSelected(null);
    setPage(next);
  }

  const entry = result?.entries.find((item) => item.id === selected);
  return <div className="archive-history">
    <input type="search" className="applications-search" aria-label="Buscar en el historial de archivo" placeholder="Buscar puesto o empresa…" value={query} maxLength={300}
      onChange={(event) => { changePage(1); setQuery(event.target.value); }} />
    {error && <p className="processes-message" role="alert">{error}</p>}
    {!result && !error && <p className="processes-message" role="status">Cargando historial…</p>}
    {result && !result.entries.length && <p className="processes-message">No hay coincidencias.</p>}
    <div className="processes-workspace">
      <ul className="processes-list">{result?.entries.map((item) => <li key={item.id}>
        <button type="button" aria-pressed={selected === item.id} onClick={() => setSelected(selected === item.id ? null : item.id)}>
          <strong>{item.title}</strong><span>{item.company || "Empresa no indicada"}</span><em title="Fecha de archivo">{formatPublicationDate(item.archived_at, true)}</em>
        </button>
      </li>)}</ul>
      {entry && <aside className="processes-detail" aria-label={`Detalle de ${entry.title}`}>
        <button type="button" className="processes-close" aria-label="Cerrar detalle" onClick={() => setSelected(null)}>×</button>
        <p className="processes-kicker">Archivado · {formatPublicationDate(entry.archived_at)}</p>
        <TrackingOfferDetail key={entry.id} item={entry}>
          {entry.notes && <p className="processes-note">{entry.notes}</p>}
        </TrackingOfferDetail>
      </aside>}
    </div>
    {(page > 1 || result?.has_more) && <nav className="archive-history-pages" aria-label="Páginas del historial">
      <button type="button" disabled={page === 1} onClick={() => changePage(page - 1)}>Anterior</button>
      <span>Página {page}</span>
      <button type="button" disabled={!result?.has_more} onClick={() => changePage(page + 1)}>Siguiente</button>
    </nav>}
  </div>;
}
