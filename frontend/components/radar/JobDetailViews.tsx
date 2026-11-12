"use client";

import JobFacts from "./JobFacts";
import { memo } from "react";
import { formatDate, formatSalary, renderMarkdown, sourceLabel, sourceName } from "../../lib/radar-format";
import type { Job } from "../../types";
import { startProcess } from "../../lib/processes-api";
import { PREPARE_CV_EVENT } from "../../lib/cv-events";
import { CompanyMapsLink, IconEyeOff, IconUndo } from "./JobCards";

export const JobReadingView = memo(function JobReadingView({
  selectedJob,
  statusBusy,
  onMarkApplied,
  onQuickHide,
  onToggleFavorite,
  onRestore,
}: {
  selectedJob: Job | null;
  statusBusy: boolean;
  onMarkApplied: (job: Job) => void;
  onQuickHide: (job: Job) => void;
  onToggleFavorite: (job: Job) => void;
  onRestore: (job: Job) => void;
}) {
  return (
    <div className="job-reading-view">
      {selectedJob ? (
        <article className="reading-card">
          <header className="reading-header">
            <div className="reading-header-top">
              <span className="reading-badge area">{selectedJob.primary_area || "General"}</span>
              <span className="reading-badge date">{formatDate(selectedJob.published_at)}</span>
              <button
                type="button"
                className={`reading-fav-btn ${selectedJob.is_favorite ? "active" : ""}`}
                aria-label={selectedJob.is_favorite ? "Quitar de favoritos (f)" : "Añadir a favoritos (f)"}
                title={selectedJob.is_favorite ? "Quitar de favoritos (f)" : "Añadir a favoritos (f)"}
                onClick={() => onToggleFavorite(selectedJob)}
              >
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
            <button className="reading-apply-toggle" type="button" onClick={() => window.dispatchEvent(new CustomEvent(PREPARE_CV_EVENT, { detail: { jobId: selectedJob.id } }))}>Preparar CV</button>
            {selectedJob.url && <a className="reading-apply-btn" href={selectedJob.url} target="_blank" rel="noreferrer">{sourceLabel(selectedJob.url)} ↗</a>}
            <button type="button" className="reading-apply-toggle applied-action" onClick={() => onMarkApplied(selectedJob)}>✓ Postulé</button>
            <button type="button" className="reading-apply-toggle" onClick={() => startProcess(selectedJob)}>Me contactaron</button>
            {selectedJob.user_status === "hidden" ? (
              <button className="restore-button icon-only" type="button" aria-label="Restaurar oferta (r)" title="Restaurar oferta (r)" disabled={statusBusy} onClick={() => onRestore(selectedJob)}><IconUndo /></button>
            ) : (
              <button className="reading-hide-trigger icon-only" type="button" aria-label="Archivar oferta (x)" title="Archivar oferta" onClick={() => onQuickHide(selectedJob)}><IconEyeOff /></button>
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
  );
});

export const MapJobPopover = memo(function MapJobPopover({
  selectedJob,
  expandedDescriptionId,
  statusBusy = false,
  onClose,
  onToggleDescription,
  onQuickHide,
  onMarkApplied,
  onRestore,
}: {
  selectedJob: Job;
  expandedDescriptionId: string | null;
  statusBusy?: boolean;
  onClose: () => void;
  onToggleDescription: (jobId: string) => void;
  onQuickHide?: (job: Job) => void;
  onMarkApplied?: (job: Job) => void;
  onRestore?: (job: Job) => void;
}) {
  return (
    <>
      <article aria-label="Detalle de la oferta" className={`job-popover ${expandedDescriptionId === selectedJob.id ? "is-description-expanded" : ""}`}>
        {onMarkApplied && (
          <button className="popover-applied-button" type="button" aria-label="Postulé" title="Postulé" disabled={statusBusy} onClick={() => onMarkApplied(selectedJob)}>
            ✓
          </button>
        )}
        {onQuickHide && selectedJob.user_status !== "hidden" && (
          <button className="hide-button popover-hide-button" type="button" aria-label="Archivar oferta" title="Archivar oferta" onClick={() => onQuickHide(selectedJob)}>
            <IconEyeOff />
          </button>
        )}
        <button className="close-button" onClick={onClose} aria-label="Cerrar detalle" type="button">×</button>
        <span className="job-area">{selectedJob.primary_area || "Sin área"}<span className="job-source"> · {sourceName(selectedJob.url)}</span></span>
        <h3>{selectedJob.url ? <a className="job-popover-title" href={selectedJob.url} target="_blank" rel="noreferrer">{selectedJob.title}</a> : selectedJob.title}</h3>
        <p className="popover-company">
          {selectedJob.company || "Empresa no indicada"}
          <CompanyMapsLink job={selectedJob} />
        </p>
        <div className="popover-divider" />
        <JobFacts job={selectedJob} />
        {selectedJob.description && (
          <div className="popover-description-wrap">
            <div
              className="description-toggle"
              role="button"
              tabIndex={0}
              aria-label="Ver descripción completa"
              title="Ver descripción completa"
              aria-expanded={expandedDescriptionId === selectedJob.id}
              onClick={() => onToggleDescription(selectedJob.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onToggleDescription(selectedJob.id);
                }
              }}
            >
              <div className="popover-description">{renderMarkdown(selectedJob.description)}</div>
            </div>
          </div>
        )}
        {selectedJob.user_status === "hidden" && onRestore && (
          <div className="popover-actions">
            <button className="restore-button icon-only" type="button" aria-label="Restaurar oferta (r)" title="Restaurar oferta (r)" disabled={statusBusy} onClick={() => onRestore(selectedJob)}>
              <IconUndo />
            </button>
          </div>
        )}
      </article>
    </>
  );
});
