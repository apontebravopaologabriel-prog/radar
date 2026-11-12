"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { applicationStatusForProcess, fetchProcesses, saveProcess, STAGES, type ProcessInput, type ProcessItem } from "../lib/processes-api";
import { isRecentArchive, trackingDay } from "../lib/tracking-dates";
import { fetchTrackingApplications, updateApplication, type TrackedApplication, type TrackingApplicationItem } from "../lib/applications-api";
import ArchiveHistory from "./ArchiveHistory";
import ProcessForm from "./ProcessForm";
import ApplicationsView from "./ApplicationsView";
import TrackingOfferDetail from "./TrackingOfferDetail";
import { IconArchive, IconRestore, IconReturn } from "./ArchiveIcon";
import "./processes.css";

function formatDate(value: string | null | undefined) {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

const TRACKING_REFRESH_MS = 1000;

function trackingChanged() {
  window.dispatchEvent(new CustomEvent("radar:jobs-changed"));
}

export default function ProcessesView({ onContextChange }: { onContextChange?: (count: number, status: string) => void }) {
  const [items, setItems] = useState<ProcessItem[] | null>(null);
  const [applications, setApplications] = useState<TrackingApplicationItem[]>([]);
  const [activity, setActivity] = useState<Record<string, number>>({});
  const [showHistory, setShowHistory] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState<ProcessInput | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState("");
  const [returning, setReturning] = useState<string | null>(null);
  const [today, setToday] = useState(trackingDay);
  const [loadError, setLoadError] = useState("");
  useEffect(() => {
    let request: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout>;
    let previous = "";
    const refresh = async () => {
      clearTimeout(timer);
      request?.abort();
      if (document.hidden) return;
      setToday(trackingDay());
      const controller = new AbortController();
      request = controller;
      try {
        const snapshot = await Promise.all([fetchProcesses(controller.signal), fetchTrackingApplications(controller.signal)]);
        if (controller.signal.aborted) return;
        const serialized = JSON.stringify(snapshot);
        if (serialized !== previous) {
          previous = serialized;
          setItems(snapshot[0]);
          setApplications(snapshot[1].applications);
          setActivity(snapshot[1].activity);
        }
        setLoadError("");
      } catch (reason) {
        if (!controller.signal.aborted) {
          setLoadError(reason instanceof Error ? reason.message : "No se pudieron cargar los procesos.");
        }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, TRACKING_REFRESH_MS);
      }
    };
    void refresh();
    window.addEventListener("radar:jobs-changed", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      request?.abort();
      clearTimeout(timer);
      window.removeEventListener("radar:jobs-changed", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);
  // A discarded application also archives its linked process.
  const discarded = useMemo(() => new Map(applications.filter((item) => item.status === "rejected" || item.status === "ignored").map((item) => [item.job_id, item])), [applications]);
  const isArchived = (item: ProcessItem) => item.stage === "closed" || (!!item.job_id && discarded.has(item.job_id));
  const submitted = useMemo(() => new Set(applications.filter((item) => item.status === "applied" || item.archived_from_applied).map((item) => item.job_id)), [applications]);
  const tracked = useMemo(() => (items ?? []).filter((item) => item.stage === "closed" || !item.job_id || !submitted.has(item.job_id)), [items, submitted]);
  const active = tracked.filter((item) => !isArchived(item));
  // The processes API orders dated commitments first and by due date.
  const nextCommitment = active.find((item) => item.due_date);
  const archivedProcesses = tracked.filter((item) => {
    if (!isArchived(item)) return false;
    const application = item.job_id ? discarded.get(item.job_id) : undefined;
    return isRecentArchive(item.archived_at ?? application?.archived_at ?? application?.updated_at ?? item.updated_at, today);
  });
  const processJobIds = useMemo(() => new Set(tracked.flatMap((item) => item.job_id ? [item.job_id] : [])), [tracked]);
  const archivedApplications = [...discarded.values()].filter((item) =>
    (item.status === "rejected" || item.applied_at) && !processJobIds.has(item.job_id) &&
    isRecentArchive(item.archived_at ?? item.updated_at, today));
  const archivedCount = archivedProcesses.length + archivedApplications.length;
  const current = (showArchived ? archivedProcesses : active).find((item) => item.id === selected);
  const archivedApplication = showArchived ? archivedApplications.find((item) => item.id === selected) : undefined;

  async function saved(item: ProcessItem) {
    setEditing(null);
    try {
      if (item.job_id) await updateApplication(item.job_id, applicationStatusForProcess(item.stage));
      trackingChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "El proceso se guardó, pero no se pudo actualizar la postulación.");
    }
  }
  async function moveStage(item: ProcessItem, stage: ProcessItem["stage"]) {
    try {
      const { id, company, title, job_id, url, next_step, due_date, notes } = item;
      await saved(await saveProcess({ company, title, job_id, url, stage, next_step, due_date, notes }, id));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo actualizar el proceso."); }
  }
  async function restoreApplication(item: TrackedApplication) {
    try {
      await updateApplication(item.job_id, "applied");
      trackingChanged();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo restaurar la postulación."); }
  }
  async function toggleProcessArchive(item: ProcessItem) {
    setError("");
    if (!item.job_id || item.stage === "closed") {
      await moveStage(item, showArchived ? "contact" : "closed");
      return;
    }
    try {
      await updateApplication(item.job_id, showArchived ? applicationStatusForProcess(item.stage) : "rejected");
      setSelected(null);
      trackingChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo actualizar el archivo.");
    }
  }

  async function returnToApplications(item: ProcessItem) {
    if (!item.job_id || returning) return;
    setReturning(item.id);
    setError("");
    try {
      await updateApplication(item.job_id, "applied");
      setSelected((currentId) => currentId === item.id ? null : currentId);
      trackingChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo devolver la oferta a Postulaciones recientes.");
    } finally {
      setReturning(null);
    }
  }

  const groups = showArchived ? [] : (["offer", "interview", "assessment", "contact"] as const).map((stage) => ({ stage, rows: active.filter((item) => (item.stage ?? "contact") === stage) })).filter((group) => group.rows.length);
  const processRow = (item: ProcessItem) => <li key={item.id}>
    <button type="button" aria-pressed={selected === item.id} onClick={() => { setSelected(selected === item.id ? null : item.id); setEditing(null); }}>
      <strong>{item.title}</strong><span>{item.company}</span>{(item.next_step || item.due_date) && <small>{item.next_step || "Fecha programada"}{item.due_date ? ` · ${formatDate(item.due_date)}` : ""}</small>}
    </button>
    {!showArchived && item.job_id && <button type="button" className="processes-icon" disabled={returning !== null} aria-label={`Devolver ${item.title} a Postulaciones recientes`} title="Volver a Postulaciones recientes" onClick={() => void returnToApplications(item)}><IconReturn /></button>}
    <button type="button" className="processes-icon" disabled={returning === item.id} aria-label={showArchived ? `Restaurar ${item.title}` : `Archivar ${item.title}`} title={showArchived ? "Restaurar" : "Archivar"} onClick={() => void toggleProcessArchive(item)}>{showArchived ? <IconRestore /> : <IconArchive />}</button>
  </li>;

  return <div className="processes-view" aria-label="Mi búsqueda">
    <header className="processes-heading"><div><p>MI BÚSQUEDA</p><h1>Procesos</h1></div><button type="button" onClick={() => { setSelected(null); setEditing({ company: "", title: "", stage: "contact" }); }}>Agregar proceso</button></header>
    <div className="processes-summary">
      {nextCommitment && <button type="button" className="processes-next" onClick={() => {
        setShowArchived(false); setShowHistory(false); setEditing(null); setSelected(nextCommitment.id);
      }}>
        <span>{(nextCommitment.due_date ?? "") < today ? "Compromiso vencido" : "Próximo compromiso"} · {formatDate(nextCommitment.due_date)}</span>
        <strong>{nextCommitment.next_step || nextCommitment.title}</strong>
      </button>}
      <div><strong>{active.length}</strong><span>En curso</span></div>
      <div><strong>{active.filter((item) => item.due_date).length}</strong><span>Con fecha programada</span></div>
    </div>
    <section className="processes-section" aria-label="Seguimiento de respuestas">
      <div className="processes-section-head"><h2>Seguimiento</h2><div role="group" aria-label="Estado de procesos"><button type="button" aria-pressed={!showArchived} onClick={() => { setShowArchived(false); setShowHistory(false); setSelected(null); setEditing(null); }}>Activos · {active.length}</button><button type="button" aria-pressed={showArchived} onClick={() => { setShowArchived(true); setShowHistory(false); setSelected(null); setEditing(null); }}>Archivados (7 días) · {archivedCount}</button></div></div>
      {error && <p role="alert" className="processes-message">{error}</p>}
      {loadError && <p role="alert" className="processes-message">{loadError} <button type="button" onClick={trackingChanged}>Reintentar</button></p>}
      {!items && !loadError && <p role="status" className="processes-message">Cargando procesos…</p>}
      {items && !showArchived && active.length === 0 && <p className="processes-message">Usa el pin de una postulación para pasarla a Entrevista.</p>}
      {showArchived && <button type="button" className="archive-history-toggle" aria-pressed={showHistory} onClick={() => {
        setSelected(null); setEditing(null); setShowHistory((value) => !value);
      }}>{showHistory ? "Volver a últimos 7 días" : "Buscar en historial"}</button>}
      {items && showArchived && !showHistory && archivedCount === 0 && <p className="processes-message">No hay elementos archivados en los últimos 7 días.</p>}
      {showHistory ? <ArchiveHistory /> : <div className="processes-workspace">
        <ul className="processes-list">
          {groups.map((group) => <Fragment key={group.stage}>
            <li className="processes-group" role="presentation">{STAGES[group.stage]} · {group.rows.length}</li>
            {group.rows.map(processRow)}
          </Fragment>)}
          {showArchived && archivedProcesses.map(processRow)}
          {showArchived && archivedApplications.map((item) => <li key={item.id}>
            <button type="button" aria-pressed={selected === item.id} onClick={() => { setSelected(selected === item.id ? null : item.id); setEditing(null); }}><strong>{item.title}</strong><span>{item.company}</span></button>
            <button type="button" className="processes-icon" aria-label={`Restaurar ${item.title}`} title="Restaurar" onClick={() => void restoreApplication(item)}><IconRestore /></button>
          </li>)}
        </ul>
        {current && !editing && <aside className="processes-detail" aria-label={`Detalle de ${current.title}`}>
          <button type="button" className="processes-close" aria-label="Cerrar detalle" onClick={() => setSelected(null)}>×</button>
          <p className="processes-kicker">{showArchived ? "Archivado" : STAGES[current.stage ?? "contact"]}</p>
          <TrackingOfferDetail key={current.id} item={current}>
            {current.next_step && <div className="processes-fact"><span>Próximo paso</span><strong>{current.next_step}</strong></div>}
            {current.due_date && <div className="processes-fact"><span>Fecha</span><strong>{formatDate(current.due_date)}</strong></div>}
            {current.notes && <p className="processes-note">{current.notes}</p>}
          </TrackingOfferDetail>
        </aside>}
        {archivedApplication && !editing && <aside className="processes-detail" aria-label={`Detalle de ${archivedApplication.title}`}>
          <button type="button" className="processes-close" aria-label="Cerrar detalle" onClick={() => setSelected(null)}>×</button>
          <p className="processes-kicker">Archivado</p>
          <TrackingOfferDetail key={archivedApplication.id} item={archivedApplication}>
            {archivedApplication.notes && <p className="processes-note">{archivedApplication.notes}</p>}
          </TrackingOfferDetail>
        </aside>}
      </div>}
      {editing && <div className="processes-editor"><ProcessForm initial={editing} onCancel={() => setEditing(null)} onSaved={(item) => void saved(item)} /></div>}
    </section>
    <ApplicationsView activity={activity} today={today} items={items ? applications : null} onChanged={trackingChanged} onContextChange={onContextChange} processJobIds={processJobIds} />
  </div>;
}
