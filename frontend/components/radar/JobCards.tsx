"use client";

import { memo, type ReactNode } from "react";
import { companyMapsUrl, formatDate, REASON_LABELS, sourceName } from "../../lib/radar-format";
import type { Job } from "../../types";

export function LoadingDots() {
  return (
    <span className="loading-dots" aria-hidden="true">
      <i /><i /><i />
    </span>
  );
}

export function IconEyeOff() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 3l18 18M10.6 6.2A9.9 9.9 0 0 1 12 6c6 0 9.5 6 9.5 6a16 16 0 0 1-3.2 3.7M6.6 7.6C4 9.3 2.5 12 2.5 12s3.5 6 9.5 6c1.5 0 2.8-.4 4-.9M9.9 9.9a2.5 2.5 0 0 0 3.2 3.2" />
    </svg>
  );
}

export function IconUndo() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 7 4 12l5 5M4 12h10a6 6 0 0 1 6 6" /></svg>;
}

export function ViewIcon({ view }: { view: "active" | "favorites" | "hidden" }) {
  if (view === "favorites") return <span aria-hidden="true">★</span>;
  if (view === "hidden") return <IconEyeOff />;
  return <span aria-hidden="true">◉</span>;
}

export function CompanyMapsLink({ job }: { job: Pick<Job, "company" | "district" | "location"> }) {
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

export function CardAction({ label, className, onAction, children }: { label: string; className: string; onAction: () => void; children: ReactNode }) {
  return (
    <span
      className={className}
      role="button"
      tabIndex={0}
      aria-label={label}
      title={label}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onAction();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          event.stopPropagation();
          onAction();
        }
      }}
    >
      {children}
    </span>
  );
}

export const OfferSignalCard = memo(function OfferSignalCard({
  job,
  selected,
  showHidden,
  onSelect,
  onToggleFavorite,
  onMarkApplied,
  onQuickHide,
  onRestore,
}: {
  job: Job;
  selected: boolean;
  showHidden: boolean;
  onSelect: (job: Job) => void;
  onToggleFavorite: (job: Job) => void;
  onMarkApplied: (job: Job) => void;
  onQuickHide: (job: Job) => void;
  onRestore: (job: Job) => void;
}) {
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
      {job.url ? <a className="offer-scroll-title" title={job.title} href={job.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>{job.title}</a> : <strong>{job.title}</strong>}
      <span className="offer-scroll-company">
        <span className="offer-company-name">{job.company || "Empresa no indicada"}<CompanyMapsLink job={job} /></span>
        <span className="offer-company-source">{sourceName(job.url)}</span>
      </span>
      <span className="offer-scroll-footer">
        <span className="offer-scroll-location">{job.district || job.location || "Ubicación pendiente"}{job.distance_km !== undefined ? ` · ${job.distance_km.toFixed(1)} km` : ""}</span>
        <span className="offer-scroll-actions">
          <CardAction className="favorite-toggle" label={job.is_favorite ? "Quitar de favoritos (f)" : "Añadir a favoritos (f)"} onAction={() => onToggleFavorite(job)}>{job.is_favorite ? "★" : "☆"}</CardAction>
          {!showHidden && <CardAction className="card-action applied" label="Marcar como postulé" onAction={() => onMarkApplied(job)}>✓</CardAction>}
          {showHidden
            ? <CardAction className="card-action restore" label="Restaurar oferta (r)" onAction={() => onRestore(job)}><IconUndo /></CardAction>
            : <CardAction className="card-action hide" label="Archivar oferta (x)" onAction={() => onQuickHide(job)}><IconEyeOff /></CardAction>}
        </span>
      </span>
    </article>
  );
});

export const JobCard = memo(function JobCard({
  job,
  selected,
  showHidden,
  onSelect,
  onToggleFavorite,
  onMarkApplied,
  onQuickHide,
  onRestore,
}: {
  job: Job;
  selected: boolean;
  showHidden: boolean;
  onSelect: (job: Job) => void;
  onToggleFavorite: (job: Job) => void;
  onMarkApplied: (job: Job) => void;
  onQuickHide: (job: Job) => void;
  onRestore: (job: Job) => void;
}) {
  return (
    <article
      className={`job-card ${selected ? "selected" : ""}`}
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
      <div className="job-card-top">
        <span className="job-area" title={job.primary_area || "Sin área"}>{job.primary_area || "Sin área"}</span>
        <span className="job-date">{formatDate(job.published_at)}</span>
        <CardAction className="favorite-toggle" label={job.is_favorite ? "Quitar de favoritos" : "Añadir a favoritos"} onAction={() => onToggleFavorite(job)}>{job.is_favorite ? "★" : "☆"}</CardAction>
        {!showHidden && <CardAction className="card-action applied" label="Marcar como postulé" onAction={() => onMarkApplied(job)}>✓</CardAction>}
        {showHidden
          ? <CardAction className="card-action restore" label="Restaurar oferta (r)" onAction={() => onRestore(job)}><IconUndo /></CardAction>
          : <CardAction className="card-action hide" label="Archivar oferta (x)" onAction={() => onQuickHide(job)}><IconEyeOff /></CardAction>}
      </div>
      <strong>{job.title}</strong>
      <span className="job-company">{job.company || "Empresa no indicada"}</span>
      <div className="job-meta">
        <span>⌖ {job.district || job.location || "Ubicación pendiente"}{job.distance_km !== undefined ? ` · ${job.distance_km.toFixed(1)} km` : ""}</span>
        <span>{job.work_mode === "hybrid" ? "Híbrido" : job.work_mode === "remote" ? "Remoto" : job.work_mode === "onsite" ? "Presencial" : "Modalidad n/i"}</span>
      </div>
      {showHidden && <span className="hidden-reason">{`> motivo=${REASON_LABELS[job.user_reason || ""] || "oculta"}`}</span>}
    </article>
  );
});
