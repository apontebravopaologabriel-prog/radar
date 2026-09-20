"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type RefreshState } from "../../lib/mobile-api";

/** Botón "Actualizar mercado ahora" con progreso; la captura corre en el equipo del usuario. */
export default function RefreshPanel({ places, onError, autoStart = false }: { places: string[]; onError: (e: unknown) => void; autoStart?: boolean }) {
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
    try { setState(await api.startRefresh(places)); poll(); } catch (error) { onError(error); }
  }, [places, poll, onError]);
  useEffect(() => { if (autoStart && !started.current) { started.current = true; void start(); } }, [autoStart, start]);

  const pct = state && state.total ? Math.round((state.done / state.total) * 100) : 0;
  return (
    <div className="m-refresh">
      <button className="m-primary" disabled={state?.running} onClick={start}>{state?.running ? `Actualizando… ${pct}%` : "Actualizar mercado ahora"}</button>
      {state?.running && <p className="m-sub">{state.done} de {state.total} búsquedas{state.current ? ` · ${state.current}` : ""}. Puedes seguir usando Radar.</p>}
      {state && !state.running && state.total > 0 && (
        <p className="m-sub">Última actualización: {state.created} ofertas nuevas{state.errors.length ? ` · ${state.errors.length} fuente(s) con error` : ""}.</p>
      )}
    </div>
  );
}
