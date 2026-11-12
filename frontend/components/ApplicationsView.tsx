"use client";

import { useEffect, useMemo, useState } from "react";
import { updateApplication, type TrackedApplication } from "../lib/applications-api";
import { daysFromTrackingDay, formatPublicationDate } from "../lib/tracking-dates";
import TrackingOfferDetail from "./TrackingOfferDetail";
import { IconArchive, IconPin } from "./ArchiveIcon";
import "./applications.css";

const WEEKS = 12;
const STALE_DAYS = 14;

function day(value: string | null | undefined) {
  if (!value) return "Fecha no indicada";
  const parsed = new Date(value.replace(" ", "T"));
  return Number.isNaN(parsed.getTime()) ? "Fecha no indicada" : new Intl.DateTimeFormat("es-PE", { day: "numeric", month: "short", year: "numeric" }).format(parsed);
}

function ago(days: number | null) {
  if (days === null) return "—";
  if (days < 1) return "hoy";
  if (days < 30) return `${days} d`;
  if (days < 70) return `${Math.floor(days / 7)} sem`;
  return `${Math.floor(days / 30)} m`;
}

export default function ApplicationsView({ items, activity, today, onContextChange, processJobIds, onChanged }: {
  items: TrackedApplication[] | null;
  activity: Record<string, number>;
  today: string;
  onContextChange?: (count: number, status: string) => void;
  processJobIds: ReadonlySet<string>;
  onChanged: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const [onlyWaiting, setOnlyWaiting] = useState(false);

  // Archived applications and those already followed as a process leave this list.
  const recent = useMemo(() => (items ?? [])
    .filter((item) => item.status === "applied" && !processJobIds?.has(item.job_id))
    .sort((a, b) => (b.applied_at ?? b.updated_at).localeCompare(a.applied_at ?? a.updated_at)), [items, processJobIds]);
  const waiting = useMemo(() => recent.filter((item) => (daysFromTrackingDay(item.applied_at, today) ?? 0) > STALE_DAYS), [recent, today]);
  const filtered = useMemo(() => (onlyWaiting ? waiting : recent).filter((item) => `${item.title} ${item.company ?? ""} ${item.location ?? ""}`.toLocaleLowerCase("es").includes(query.trim().toLocaleLowerCase("es"))), [recent, waiting, onlyWaiting, query]);
  const visible = showAll || query.trim() || onlyWaiting ? filtered : filtered.slice(0, 8);
  const active = visible.find((item) => item.id === selected) ?? null;
  const rhythm = useMemo(() => {
    const weeks = Array.from({ length: WEEKS }, () => 0);
    let oldest = 0;
    let total = 0;
    for (const [date, count] of Object.entries(activity)) {
      const age = daysFromTrackingDay(`${date}T12:00:00-05:00`, today);
      if (age === null || age < 0) continue;
      oldest = Math.max(oldest, age);
      total += count;
      const week = Math.floor(age / 7);
      if (week < WEEKS) weeks[WEEKS - 1 - week] += count;
    }
    return { weeks, max: Math.max(1, ...weeks), oldest, perWeek: total / Math.max(1, oldest / 7), total };
  }, [activity, today]);
  useEffect(() => { if (items) onContextChange?.(recent.length, "applied"); }, [items, recent.length, onContextChange]);

  async function move(item: TrackedApplication, status: "interview" | "rejected") {
    setPending((current) => new Set(current).add(item.id));
    setError("");
    try {
      await updateApplication(item.job_id, status);
      setSelected((current) => current === item.id ? null : current);
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo mover la postulación.");
    } finally {
      setPending((current) => new Set([...current].filter((id) => id !== item.id)));
    }
  }

  return <section className="applications-view" aria-label="Postulaciones recientes">
    <div className="applications-section-head">
      <h2>Postulaciones recientes <span>{recent.length}</span></h2>
      {!onlyWaiting && !query.trim() && recent.length > 8 && <button type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? "Ver recientes" : `Ver todas (${recent.length})`}</button>}
    </div>
    {rhythm.total > 0 && <div className="applications-rhythm" aria-label="Ritmo de búsqueda" title="Solo cuenta lo registrado en Radar">
      <div className="applications-rhythm-bars" role="img" aria-label={`Postulaciones por semana, últimas ${WEEKS} semanas: ${rhythm.weeks.join(", ")}`}>{rhythm.weeks.map((count, index) => <i key={index} title={`${count} postulaciones`} style={{ height: `${Math.max(count ? 12 : 3, (count / rhythm.max) * 100)}%` }} />)}</div>
      <dl><div><dt>Buscando desde hace</dt><dd>{rhythm.oldest} días</dd></div><div><dt>Ritmo</dt><dd>{rhythm.perWeek.toFixed(1)} / semana</dd></div><div><dt><button type="button" aria-pressed={onlyWaiting} onClick={() => setOnlyWaiting((value) => !value)}>Sin respuesta · +{STALE_DAYS} d</button></dt><dd>{waiting.length}</dd></div></dl>
    </div>}
    {recent.length > 0 && <input className="applications-search" type="search" aria-label="Buscar postulaciones" placeholder="Buscar puesto o empresa…" value={query} onChange={(event) => setQuery(event.target.value)} />}
    {error && <p className="applications-message" role="alert">{error}</p>}
    {items && !filtered.length && <p className="applications-message">{query.trim() ? "Sin coincidencias." : onlyWaiting ? "No hay postulaciones sin respuesta de más de 14 días." : "No hay postulaciones recientes."}</p>}
    <div className="applications-workspace">
      <ul className="applications-list">{visible.map((item) => <li key={item.id}>
        <button type="button" className="applications-row" aria-pressed={selected === item.id} onClick={() => setSelected(selected === item.id ? null : item.id)}>
          <span className="applications-date" title={`Publicado · ${formatPublicationDate(item.published_at)}`}>
            <span className="applications-date-label">Publicado: </span>{formatPublicationDate(item.published_at, true)}
          </span>
          <span className="applications-role">{item.title}</span>
          <span className="applications-company">{item.company || "Empresa no indicada"}</span>
          <span className="applications-age" title={`Postulé · ${day(item.applied_at)}`}>
            <span className="applications-date-label">Postulé: </span>{ago(daysFromTrackingDay(item.applied_at, today))}
          </span>
        </button>
        <button type="button" className="applications-action" disabled={pending.has(item.id)} aria-label={`Pasar ${item.title} a Entrevista`} title="Pasar a Entrevista" onClick={() => void move(item, "interview")}><IconPin /></button>
        <button type="button" className="applications-action" disabled={pending.has(item.id)} aria-label={`Archivar ${item.title}`} title="Archivar" onClick={() => void move(item, "rejected")}><IconArchive /></button>
      </li>)}</ul>
      {active && <aside className="applications-detail" aria-label={`Detalle de ${active.title}`}>
        <button type="button" className="applications-close" aria-label="Cerrar detalle" onClick={() => setSelected(null)}>×</button>
        <p className="applications-kicker">Postulé · {day(active.applied_at)}</p>
        <TrackingOfferDetail key={active.id} item={active}>
          {active.notes && <p className="applications-note">{active.notes}</p>}
        </TrackingOfferDetail>
      </aside>}
    </div>
  </section>;
}
