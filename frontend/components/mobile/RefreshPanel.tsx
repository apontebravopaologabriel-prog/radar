"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type RefreshState, type Career } from "../../lib/mobile-api";

/** Botón "Actualizar mercado ahora" con progreso; la captura corre en el equipo del usuario. */
export default function RefreshPanel({ places, onError, autoStart = false, chooseMarkets = false }: { places: string[]; onError: (e: unknown) => void; autoStart?: boolean; chooseMarkets?: boolean }) {
  const [markets, setMarkets] = useState<Career["tracks"]>([]);
  const [target, setTarget] = useState("industrial_engineering");
  useEffect(() => {
    if (!chooseMarkets) return;
    api.career().then((career) => { setMarkets(career.tracks); setTarget((old) => career.tracks.some((m) => m.id === old) ? old : career.active); }).catch(onError);
    try { const saved = localStorage.getItem("radar.market"); if (saved) setTarget(saved); } catch { /* Storage is optional. */ }
  }, [chooseMarkets, onError]);
  const [state, setState] = useState<RefreshState | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const started = useRef(false);

  const poll = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const next = await api.refreshStatus();
        setState(next);
        if (!next.running && timer.current) { clearInterval(timer.current); timer.current = null; }
      } catch (error) { onError(error); if (timer.current) clearInterval(timer.current); }
    }, 2000);
  }, [onError]);
  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);
  useEffect(() => { api.refreshStatus().then((s) => { setState(s); if (s.running) poll(); }).catch(() => undefined); }, [poll]);

  const start = useCallback(async () => {
    try { setState(await api.startRefresh(places, chooseMarkets ? (target === "both" ? markets.filter((m) => !m.name.includes("experimental")).map((m) => m.id) : [target]) : undefined)); poll(); } catch (error) { onError(error); }
  }, [places, poll, onError, chooseMarkets, target, markets]);
  useEffect(() => { if (autoStart && !started.current) { started.current = true; void start(); } }, [autoStart, start]);

  const pct = state && state.total ? Math.round((state.done / state.total) * 100) : 0;
  return (
    <div className="m-refresh">
      {chooseMarkets && <label>Mercado a actualizar<select value={target} disabled={state?.running} onChange={(event) => setTarget(event.target.value)}>{markets.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}<option value="both">Mercados principales</option></select></label>}
      <button className="m-primary" disabled={state?.running} onClick={start}>{state?.running ? `Actualizando… ${pct}%` : "Actualizar mercado ahora"}</button>
      {state?.running && <p className="m-sub">{state.done} de {state.total} búsquedas{state.current ? ` · ${state.current}` : ""}. Puedes seguir usando Radar.</p>}
      {state && !state.running && state.total > 0 && (
        <p className="m-sub">Última actualización: {state.created} ofertas nuevas{state.errors.length ? ` · ${state.errors.length} fuente(s) con error` : ""}.</p>
      )}
    </div>
  );
}
