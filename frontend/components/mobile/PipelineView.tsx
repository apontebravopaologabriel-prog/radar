"use client";

import { useCallback, useEffect, useState } from "react";
import { api, STATUS_LABELS, STATUS_ORDER, type AgentContext, type Application } from "../../lib/mobile-api";

const NEXT: Record<string, string | null> = { saved: "applied", applied: "interview", interview: "offer", offer: null, rejected: "saved" };
const NEXT_LABEL: Record<string, string> = { applied: "Ya postulé", interview: "Me citaron", offer: "Recibí oferta", saved: "Reabrir" };

function daysSince(iso: string | null): number | null {
  return iso ? Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000) : null;
}

export default function PipelineView({ onError, onContextChange }: { onError: (e: unknown) => void; onContextChange?: (context: AgentContext) => void }) {
  const [items, setItems] = useState<Application[] | null>(null);
  const [tab, setTab] = useState("saved");

  const load = useCallback(async () => {
    try { setItems((await api.applications()).applications); } catch (error) { onError(error); }
  }, [onError]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!items) return;
    onContextChange?.({ screen: "pipeline", filters: { status: tab }, visibleCount: items.filter((i) => i.status === tab).length });
  }, [items, tab, onContextChange]);

  const move = async (item: Application, status: string) => {
    try { await api.setApplication(item.job_id, status); await load(); } catch (error) { onError(error); }
  };

  if (!items) return <p className="m-empty">Cargando…</p>;
  const counts = (s: string) => items.filter((i) => i.status === s).length;
  const shown = items.filter((i) => i.status === tab);
  return (
    <div className="m-stack">
      <header className="m-head"><span className="m-eyebrow">[SEGUIMIENTO]</span><h1>Seguimiento</h1><p>Tu proceso, de guardada a oferta</p></header>
      <div className="m-chips" role="tablist">
        {STATUS_ORDER.map((s) => (
          <button key={s} role="tab" aria-selected={tab === s} onClick={() => setTab(s)}>{STATUS_LABELS[s]} <b>{counts(s)}</b></button>
        ))}
      </div>
      {shown.length === 0 && <p className="m-empty">Sin ofertas en «{STATUS_LABELS[tab]}».</p>}
      {shown.map((item) => {
        const waiting = item.status === "applied" ? daysSince(item.applied_at ?? item.updated_at) : null;
        const next = NEXT[item.status];
        return (
          <article className="m-card" key={item.id}>
            <h2>{item.title}</h2>
            <p className="m-sub">{item.company ?? "Empresa sin nombre"}</p>
            {waiting !== null && waiting >= 7 && <p className="m-why">Hace {waiting} días sin novedad: considera hacer seguimiento.</p>}
            <div className="m-actions">
              {next && <button onClick={() => move(item, next)}>{NEXT_LABEL[next]}</button>}
              {item.status !== "rejected" && <button onClick={() => move(item, "rejected")}>Descartar</button>}
              {item.url && <a href={item.url} target="_blank" rel="noopener noreferrer">Abrir ↗</a>}
            </div>
          </article>
        );
      })}
    </div>
  );
}
