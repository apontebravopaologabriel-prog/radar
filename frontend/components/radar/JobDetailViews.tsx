"use client";

import PreparedCvList from "../PreparedCvList";
import { memo } from "react";
import { formatDate, formatSalary, renderMarkdown, sourceLabel, sourceName } from "../../lib/radar-format";
import type { Job } from "../../types";
import { startProcess } from "../../lib/processes-api";
import { PREPARE_CV_EVENT } from "../../lib/cv-events";
import { CompanyMapsLink, IconEyeOff, IconUndo } from "./JobCards";

export const JobReadingView = memo(function JobReadingView({
  selectedJob,
  statusBusy,
  hideReasonFor,
  hideReason,
  onToggleFavorite,
  onRestore,
  onOpenHideForm,
  onCancelHideForm,
  onChangeHideReason,
  onConfirmHide,
}: {
  selectedJob: Job | null;
  statusBusy: boolean;
  hideReasonFor: string | null;
  hideReason: string;
  onToggleFavorite: (job: Job) => void;
  onRestore: (job: Job) => void;
  onOpenHideForm: (jobId: string) => void;
  onCancelHideForm: () => void;
  onChangeHideReason: (reason: string) => void;
  onConfirmHide: () => void;
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
<button type="button" className="reading-apply-toggle" onClick={() => startProcess(selectedJob)}>Me contactaron</button>
            {selectedJob.user_status === "hidden" ? (
              <button className="restore-button icon-only" type="button" aria-label="Restaurar oferta (r)" title="Restaurar oferta (r)" disabled={statusBusy} onClick={() => onRestore(selectedJob)}><IconUndo /></button>
            ) : hideReasonFor === selectedJob.id ? (
              <div className="reading-hide-form">
                <select value={hideReason} onChange={(e) => onChangeHideReason(e.target.value)}>
                  <option value="" disabled>Selecciona un motivo</option>
                  <option value="closed">Ya cerró</option>
                  <option value="not_interested">No me interesa</option>
                  <option value="duplicate">Oferta duplicada</option>
                  <option value="other">Otro</option>
                </select>
                <button className="restore-button" type="button" disabled={statusBusy || !hideReason} onClick={onConfirmHide}>{statusBusy ? "Guardando…" : "Confirmar"}</button>
                <button className="cancel-hide" type="button" onClick={onCancelHideForm}>Cancelar</button>
              </div>
            ) : (
              <button className="reading-hide-trigger icon-only" type="button" aria-label="Ocultar oferta (x)" title="Ocultar oferta (x)" onClick={() => onOpenHideForm(selectedJob.id)}><IconEyeOff /></button>
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
  hideReasonFor,
  hideReason,
  statusBusy,
  onClose,
  onOpenStudio,
  onToggleDescription,
  onOpenHideForm,
  onCancelHideForm,
  onChangeHideReason,
  onConfirmHide,
  onRestore,
}: {
  selectedJob: Job;
  expandedDescriptionId: string | null;
  hideReasonFor: string | null;
  hideReason: string;
  statusBusy: boolean;
  onClose: () => void;
  onOpenStudio: (jobId: string) => void;
  onToggleDescription: (jobId: string) => void;
  onOpenHideForm: (jobId: string) => void;
  onCancelHideForm: () => void;
  onChangeHideReason: (reason: string) => void;
  onConfirmHide: () => void;
  onRestore: (job: Job) => void;
}) {
  return (
    <>
      <article className={`job-popover ${expandedDescriptionId === selectedJob.id ? "is-description-expanded" : ""}`}>
        {selectedJob.user_status !== "hidden" && (
          <button className="hide-button popover-hide-button" type="button" aria-label="Ocultar oferta" title="Ocultar oferta" onClick={() => onOpenHideForm(selectedJob.id)}>
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
        <div className="popover-grid">
          <div><span>Ubicación</span><strong>{selectedJob.district || selectedJob.location || "Pendiente"}</strong></div>
          <div><span>Modalidad</span><strong>{selectedJob.work_mode === "hybrid" ? "Híbrido" : selectedJob.work_mode === "remote" ? "Remoto" : selectedJob.work_mode === "onsite" ? "Presencial" : "No indicada"}</strong></div>
          <div><span>Salario</span><strong>{formatSalary(selectedJob)}</strong></div>
          <div><span>Publicado</span><strong>{formatDate(selectedJob.published_at)}</strong></div>
          <div><span>Estado de publicación</span><strong>{selectedJob.application_status === "closed" ? "Cerrada" : selectedJob.application_status === "expired" ? "Vencida" : selectedJob.application_status === "open" ? "Abierta según última consulta" : "Vigencia sin verificar"}</strong></div>
        </div>
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
        <PreparedCvList jobId={selectedJob.id} />
        <div className="popover-actions"><button type="button" className="popover-prepare-cv" onClick={() => startProcess(selectedJob)}>Me contactaron</button>
          <button className="popover-prepare-cv" type="button" onClick={() => onOpenStudio(selectedJob.id)}>Preparar CV</button>
          {selectedJob.user_status === "hidden" && (
            <button className="restore-button icon-only" type="button" aria-label="Restaurar oferta (r)" title="Restaurar oferta (r)" disabled={statusBusy} onClick={() => onRestore(selectedJob)}>
              <IconUndo />
            </button>
          )}
        </div>
      </article>
      {hideReasonFor === selectedJob.id && selectedJob.user_status !== "hidden" && (
        <aside className="hide-reason-popover" aria-label="Motivo para ocultar oferta">
          <button className="hide-reason-close" type="button" aria-label="Cerrar ocultar oferta" onClick={onCancelHideForm}>×</button>
          <span className="job-area">Ocultar oferta</span>
          <strong>¿Por qué no quieres verla?</strong>
          <label>
            Motivo
            <select value={hideReason} onChange={(event) => onChangeHideReason(event.target.value)}>
              <option value="" disabled>Selecciona un motivo</option>
              <option value="closed">Ya cerró</option>
              <option value="not_interested">No me interesa</option>
              <option value="duplicate">Oferta duplicada</option>
              <option value="other">Otro</option>
            </select>
          </label>
          <button className="restore-button" type="button" disabled={statusBusy || !hideReason} onClick={onConfirmHide}>
            {statusBusy ? "Guardando…" : "Confirmar ocultar"}
          </button>
          <button className="cancel-hide" type="button" onClick={onCancelHideForm}>Cancelar</button>
        </aside>
      )}
    </>
  );
});
