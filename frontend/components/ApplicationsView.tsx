"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchApplications, updateApplication, type TrackedApplication } from "../lib/api";
import { studioApi, type StudioPackage } from "../lib/cv-studio-api";
import "./applications.css";

const TABS = [["applied", "Postulé"], ["interview", "Entrevista"], ["offer", "Oferta"], ["rejected", "Descartadas"], ["saved", "Guardadas"]] as const;
const MOVES: Record<string, [string, string][]> = {
  saved: [["applied", "Ya postulé"]],
  applied: [["interview", "Me citaron"], ["rejected", "Descartar"]],
  interview: [["offer", "Recibí oferta"], ["rejected", "Descartar"]],
  offer: [["rejected", "Descartar"]],
  rejected: [["saved", "Reabrir"]],
};

function daysSince(iso: string | null): number | null {
  return iso ? Math.max(0, Math.floor((Date.now() - new Date(iso.replace(" ", "T")).getTime()) / 86_400_000)) : null;
}

function formatDay(iso: string | null): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("es-PE", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(iso.replace(" ", "T")));
}

export default function ApplicationsView({ onContextChange }: { onContextChange?: (count: number, status: string) => void }) {
  const [items, setItems] = useState<TrackedApplication[] | null>(null);
  const [packages, setPackages] = useState<Record<string, StudioPackage>>({});
  const [tab, setTab] = useState<string>("applied");
  const [error, setError] = useState<string | null>(null);

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

  const counts = useMemo(() => Object.fromEntries(TABS.map(([status]) => [status, (items ?? []).filter((item) => item.status === status).length])), [items]);
  const shown = useMemo(() => (items ?? []).filter((item) => item.status === tab).sort((a, b) => (b.applied_at ?? b.updated_at).localeCompare(a.applied_at ?? a.updated_at)), [items, tab]);

  useEffect(() => { if (items) onContextChange?.(shown.length, tab); }, [items, shown.length, tab, onContextChange]);

  async function move(item: TrackedApplication, status: string) {
    try { await updateApplication(item.job_id, status, item.notes); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo actualizar"); }
  }

  async function openFolder(jobId: string) {
    try { await studioApi.openFolder(jobId); } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo abrir la carpeta"); }
  }

  return (
    <section className="applications-view" aria-label="Postulaciones">
      <header className="applications-head">
        <h2>Postulaciones</h2>
        <p>Dónde postulaste y en qué va cada proceso. Radar solo registra: la postulación la haces tú en el portal.</p>
      </header>
      <div className="view-tabs applications-tabs" role="tablist" aria-label="Estado de la postulación">
        {TABS.map(([status, label]) => (
          <button key={status} type="button" role="tab" aria-selected={tab === status} className={`view-tab ${tab === status ? "active" : ""}`} onClick={() => setTab(status)}>{label} <b>{counts[status] ?? 0}</b></button>
        ))}
      </div>
      {error && <p className="applications-error" role="alert">{error}</p>}
      {!items && !error && <p className="applications-empty">Cargando…</p>}
      {items && shown.length === 0 && (
        <p className="applications-empty">
          {tab === "applied" ? "Aún no registras postulaciones. Abre una oferta en el mapa y pulsa «Ya postulé», o prepara tu CV en el Estudio y pulsa «Ya la envié»." : "Sin ofertas en este estado."}
        </p>
      )}
      <ul className="applications-list">
        {shown.map((item) => {
          const pkg = packages[item.job_id];
          const waiting = item.status === "applied" ? daysSince(item.applied_at ?? item.updated_at) : null;
          return (
            <li key={item.id} className="applications-row">
              <div className="applications-main">
                <strong>{item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a> : item.title}</strong>
                <small>{item.company ?? "Empresa sin nombre"} · {item.applied_at ? `postulé el ${formatDay(item.applied_at)}` : `actualizada el ${formatDay(item.updated_at)}`}</small>
                {waiting !== null && waiting >= 7 && <small className="applications-nudge">Hace {waiting} días sin novedad: considera hacer seguimiento.</small>}
                {item.notes && <small className="applications-notes">{item.notes}</small>}
                {pkg && (
                  <small className="applications-files">
                    {pkg.files.filter((file) => file.exists !== false).map((file) => <a key={file.name} href={studioApi.fileUrl(item.job_id, file.name)} target="_blank" rel="noopener noreferrer">{file.name}</a>)}
                    {pkg.folder_exists && <button type="button" onClick={() => void openFolder(item.job_id)}>Abrir carpeta</button>}
                  </small>
                )}
              </div>
              <div className="applications-actions">
                {(MOVES[item.status] ?? []).map(([status, label]) => <button key={status} type="button" onClick={() => void move(item, status)}>{label}</button>)}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
