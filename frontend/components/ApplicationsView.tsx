"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { fetchApplications, importJobUrl, removeApplication, updateApplication, type TrackedApplication } from "../lib/api";
import { studioApi, type StudioPackage } from "../lib/cv-studio-api";
import { OPEN_JOB_EVENT } from "./agent/Markdown";
import "./applications.css";

const TABS = [
  ["applied", "Postulé"],
  ["interview", "Entrevista"],
  ["offer", "Oferta"],
  ["rejected", "Descartadas"],
  ["saved", "Guardadas"],
  ["all", "Todas"],
] as const;

const STATUS_LABELS: Record<string, string> = {
  saved: "Guardada",
  applied: "Postulé",
  interview: "Entrevista",
  offer: "Oferta",
  rejected: "Descartada",
  ignored: "Oculta",
};

const MOVES: Record<string, [string, string][]> = {
  saved: [["applied", "Ya postulé"]],
  applied: [["interview", "Me citaron"], ["rejected", "Descartar"]],
  interview: [["offer", "Recibí oferta"], ["rejected", "Descartar"]],
  offer: [["rejected", "Descartar"]],
  rejected: [["applied", "Reabrir postulación"], ["saved", "Mover a guardadas"]],
};

function daysSince(iso: string | null): number | null {
  return iso ? Math.max(0, Math.floor((Date.now() - new Date(iso.replace(" ", "T")).getTime()) / 86_400_000)) : null;
}

function formatDay(iso: string | null): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("es-PE", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(iso.replace(" ", "T")));
}

function formatWorkMode(mode?: string | null): string | null {
  if (mode === "remote") return "Remoto";
  if (mode === "hybrid") return "Híbrido";
  if (mode === "onsite") return "Presencial";
  return null;
}

function formatAppSalary(item: TrackedApplication): string | null {
  const min = item.salary_min ?? null;
  const max = item.salary_max ?? null;
  if (min === null && max === null) return null;
  const symbol = item.salary_currency === "USD" ? "US$" : "S/";
  if (min !== null && max !== null && min !== max) return `${symbol} ${Math.round(min)}–${Math.round(max)}`;
  return `${symbol} ${Math.round(min ?? max ?? 0)}`;
}

function csvCell(value: unknown): string {
  const str = String(value ?? "").replace(/"/g, '""');
  return `"${str}"`;
}

export default function ApplicationsView({ onContextChange }: { onContextChange?: (count: number, status: string) => void }) {
  const [items, setItems] = useState<TrackedApplication[] | null>(null);
  const [packages, setPackages] = useState<Record<string, StudioPackage>>({});
  const [tab, setTab] = useState<string>("applied");
  const [query, setQuery] = useState<string>("");
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState<boolean>(false);
  const [importUrl, setImportUrl] = useState<string>("");
  const [importTitle, setImportTitle] = useState<string>("");
  const [importCompany, setImportCompany] = useState<string>("");
  const [importStatus, setImportStatus] = useState<string>("applied");
  const [importBusy, setImportBusy] = useState<boolean>(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const [apps, pkgs] = await Promise.all([fetchApplications(signal), studioApi.packages().catch(() => ({ packages: [] as StudioPackage[] }))]);
      setItems(apps);
      setPackages(Object.fromEntries(pkgs.packages.map((pkg) => [pkg.job_id, pkg])));
      setError(null);
    } catch (reason) {
      if (!signal?.aborted) setError(reason instanceof Error ? reason.message : "No se pudo cargar el seguimiento");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    const onChanged = () => { void load(); };
    window.addEventListener("radar:jobs-changed", onChanged);
    return () => window.removeEventListener("radar:jobs-changed", onChanged);
  }, [load]);

  const counts = useMemo(() => {
    const list = items ?? [];
    const byStatus = Object.fromEntries(TABS.map(([status]) => [status, status === "all" ? list.length : list.filter((item) => item.status === status).length]));
    return byStatus;
  }, [items]);

  const shown = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return (items ?? [])
      .filter((item) => (tab === "all" ? true : item.status === tab))
      .filter((item) => {
        if (!normalized) return true;
        const haystack = [item.title, item.company, item.location, item.primary_area, item.notes].filter(Boolean).join(" ").toLowerCase();
        return haystack.includes(normalized);
      })
      .sort((a, b) => (b.applied_at ?? b.updated_at).localeCompare(a.applied_at ?? a.updated_at));
  }, [items, tab, query]);

  useEffect(() => { if (items) onContextChange?.(shown.length, tab); }, [items, shown.length, tab, onContextChange]);

  function notifyJobsChanged(jobId: string, status: string) {
    window.dispatchEvent(new CustomEvent("radar:jobs-changed", { detail: { name: "track_job_application", arguments: { job_id: jobId, status } } }));
  }

  async function submitImportUrl(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedUrl = importUrl.trim();
    if (!trimmedUrl) return;
    setImportBusy(true);
    setError(null);
    try {
      const res = await importJobUrl({
        url: trimmedUrl,
        title: importTitle.trim() || undefined,
        company: importCompany.trim() || undefined,
        application_status: importStatus,
      });
      setImportUrl("");
      setImportTitle("");
      setImportCompany("");
      setImportOpen(false);
      if (tab !== "all" && tab !== importStatus) setTab(importStatus);
      await load();
      notifyJobsChanged(res.job_id, importStatus);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo importar el enlace");
    } finally {
      setImportBusy(false);
    }
  }

  async function move(item: TrackedApplication, status: string) {
    try {
      await updateApplication(item.job_id, status, item.notes);
      await load();
      notifyJobsChanged(item.job_id, status);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo actualizar");
    }
  }

  async function saveNote(item: TrackedApplication) {
    const trimmed = noteDraft.trim();
    setEditingNoteId(null);
    try {
      await updateApplication(item.job_id, item.status, trimmed || null);
      await load();
      notifyJobsChanged(item.job_id, item.status);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la nota");
    }
  }

  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  async function remove(item: TrackedApplication) {
    if (confirmRemove !== item.job_id) { setConfirmRemove(item.job_id); return; }
    setConfirmRemove(null);
    try {
      await removeApplication(item.job_id);
      await load();
      notifyJobsChanged(item.job_id, "visible");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo quitar");
    }
  }

  async function openFolder(jobId: string) {
    try { await studioApi.openFolder(jobId); } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo abrir la carpeta"); }
  }

  function openInMap(jobId: string) {
    window.dispatchEvent(new CustomEvent(OPEN_JOB_EVENT, { detail: { id: jobId } }));
  }

  function exportCsv() {
    const list = items ?? [];
    if (list.length === 0) return;
    const headers = ["Estado", "Puesto", "Empresa", "Área", "Ubicación", "Modalidad", "Salario", "Fecha postulación", "Última actualización", "Notas", "URL"];
    const rows = list.map((item) => [
      STATUS_LABELS[item.status] ?? item.status,
      item.title ?? "",
      item.company ?? "",
      item.primary_area ?? "",
      item.location ?? "",
      formatWorkMode(item.work_mode) ?? "",
      formatAppSalary(item) ?? "",
      item.applied_at ?? "",
      item.updated_at ?? "",
      item.notes ?? "",
      item.url ?? "",
    ].map(csvCell).join(","));
    const csv = "\uFEFF" + [headers.map(csvCell).join(","), ...rows].join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `radar-postulaciones-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="applications-view" aria-label="Postulaciones">
      <header className="applications-head">
        <div>
          <h2>Postulaciones</h2>
          <p>Dónde postulaste y en qué va cada proceso. Al marcar «✓ Postulé» en una oferta, sale de tu bandeja activa y pasa a este registro.</p>
        </div>
        <div className="applications-toolbar">
          <input
            type="search"
            className="applications-search"
            placeholder="Filtrar por puesto, empresa, área o nota…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Filtrar postulaciones"
          />
          <button type="button" className={`applications-export ${importOpen ? "active" : ""}`} onClick={() => setImportOpen((curr) => !curr)} title="Importar una oferta externa pegando su link de Computrabajo, LinkedIn, Bumeran, etc.">
            {importOpen ? "× Cerrar" : "+ Agregar por link"}
          </button>
          <button type="button" className="applications-export" disabled={!items || items.length === 0} onClick={exportCsv} title="Exportar todas tus postulaciones a CSV compatible con Excel">
            Exportar CSV
          </button>
        </div>
      </header>
      {importOpen && (
        <form className="applications-import-bar" onSubmit={(event) => void submitImportUrl(event)}>
          <input
            type="url"
            required
            className="applications-import-url"
            placeholder="Pega el link de la oferta (Computrabajo, LinkedIn, Bumeran, Empleos Perú…)"
            value={importUrl}
            onChange={(event) => setImportUrl(event.target.value)}
            disabled={importBusy}
          />
          <input
            type="text"
            className="applications-import-meta"
            placeholder="Título (opcional si el portal es privado)"
            value={importTitle}
            onChange={(event) => setImportTitle(event.target.value)}
            disabled={importBusy}
          />
          <input
            type="text"
            className="applications-import-meta"
            placeholder="Empresa (opcional)"
            value={importCompany}
            onChange={(event) => setImportCompany(event.target.value)}
            disabled={importBusy}
          />
          <select value={importStatus} onChange={(event) => setImportStatus(event.target.value)} disabled={importBusy} aria-label="Estado inicial">
            <option value="applied">✓ Postulé</option>
            <option value="saved">Guardada (por postular)</option>
            <option value="interview">Entrevista</option>
          </select>
          <button type="submit" disabled={importBusy || !importUrl.trim()}>
            {importBusy ? "Importando…" : "Importar oferta"}
          </button>
        </form>
      )}
      <div className="view-tabs applications-tabs" role="tablist" aria-label="Estado de la postulación">
        {TABS.map(([status, label]) => (
          <button key={status} type="button" role="tab" aria-selected={tab === status} className={`view-tab ${tab === status ? "active" : ""}`} onClick={() => setTab(status)}>{label} <b>{counts[status] ?? 0}</b></button>
        ))}
      </div>
      {error && <p className="applications-error" role="alert">{error}</p>}
      {!items && !error && <p className="applications-empty">Cargando…</p>}
      {items && shown.length === 0 && (
        <p className="applications-empty">
          {query.trim()
            ? "Ninguna postulación coincide con tu búsqueda."
            : tab === "applied"
              ? "Aún no registras postulaciones. Pulsa «✓» en cualquier tarjeta de oferta o usa «+ Agregar por link»."
              : "Sin ofertas en este estado."}
        </p>
      )}
      <ul className="applications-list">
        {shown.map((item) => {
          const pkg = packages[item.job_id];
          const waiting = item.status === "applied" ? daysSince(item.applied_at ?? item.updated_at) : null;
          const workMode = formatWorkMode(item.work_mode);
          const salary = formatAppSalary(item);
          const metaParts = [
            item.company ?? "Empresa sin nombre",
            item.primary_area || null,
            item.location || null,
            workMode,
            salary,
            item.applied_at ? `postulé el ${formatDay(item.applied_at)}` : `actualizada el ${formatDay(item.updated_at)}`,
          ].filter(Boolean);
          const isEditingNote = editingNoteId === item.job_id;
          return (
            <li key={item.id} className="applications-row">
              <div className="applications-main">
                <div className="applications-title-row">
                  {tab === "all" && <span className="applications-status-badge">{STATUS_LABELS[item.status] ?? item.status}</span>}
                  <strong>{item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title} ↗</a> : item.title}</strong>
                </div>
                <small>{metaParts.join(" · ")}</small>
                {waiting !== null && waiting >= 7 && <small className="applications-nudge">Hace {waiting} días sin novedad: considera hacer seguimiento.</small>}
                {isEditingNote ? (
                  <div className="applications-note-editor">
                    <input
                      type="text"
                      value={noteDraft}
                      placeholder="Ej. CV enviado por Bumeran, contacto RRHH, pretensión salarial…"
                      onChange={(event) => setNoteDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void saveNote(item);
                        if (event.key === "Escape") setEditingNoteId(null);
                      }}
                      autoFocus
                    />
                    <button type="button" onClick={() => void saveNote(item)}>Guardar</button>
                    <button type="button" onClick={() => setEditingNoteId(null)}>Cancelar</button>
                  </div>
                ) : (
                  <div className="applications-note-row">
                    {item.notes ? (
                      <button type="button" className="applications-notes-btn" onClick={() => { setEditingNoteId(item.job_id); setNoteDraft(item.notes ?? ""); }} title="Editar nota">
                        “{item.notes}”
                      </button>
                    ) : (
                      <button type="button" className="applications-add-note" onClick={() => { setEditingNoteId(item.job_id); setNoteDraft(""); }}>
                        + Nota
                      </button>
                    )}
                  </div>
                )}
                {pkg && (
                  <small className="applications-files">
                    {pkg.files.filter((file) => file.exists !== false).map((file) => <a key={file.name} href={studioApi.fileUrl(item.job_id, file.name)} target="_blank" rel="noopener noreferrer">{file.name}</a>)}
                    {pkg.folder_exists && <button type="button" onClick={() => void openFolder(item.job_id)}>Abrir carpeta</button>}
                  </small>
                )}
              </div>
              <div className="applications-actions">
                <button type="button" onClick={() => openInMap(item.job_id)} title="Abrir la ficha de esta oferta en el mapa">Ver ficha</button>
                {(MOVES[item.status] ?? []).map(([status, label]) => <button key={status} type="button" onClick={() => void move(item, status)}>{label}</button>)}
                <button type="button" className="applications-remove" title="Quita esta oferta del seguimiento y la devuelve a las ofertas activas. No borra la oferta." onClick={() => void remove(item)} onBlur={() => setConfirmRemove(null)}>{confirmRemove === item.job_id ? "¿Seguro?" : "Quitar"}</button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
