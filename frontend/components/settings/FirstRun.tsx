"use client";

import { useCallback, useEffect, useState } from "react";
import "./terminal.css";
import Onboarding from "./Onboarding";
import { setupApi } from "../../lib/setup-api";



/** Primer inicio en escritorio: si no hay perfil, ofrece las preguntas de bienvenida en una ventana. */
export default function FirstRun() {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const onError = useCallback((e: unknown) => setError(e instanceof Error ? e.message : "Error desconocido"), []);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("inicio")) { setOpen(true); return; }
    setupApi.state().then((s) => setOpen(!s.completed)).catch(() => undefined);
  }, []);

  const close = (remember: boolean) => {
    if (remember) window.history.replaceState(null, "", "/radar");
    setOpen(false);
  };
  if (!open) return null;
  return (
    <div className="firstrun-backdrop" role="dialog" aria-modal="true" aria-label="Bienvenida a Radar">
      <div className="m-app firstrun-window">
        <div className="firstrun-bar"><span>[INICIO]</span><button type="button" aria-label="Cerrar configuración" onClick={() => close(true)}>Cerrar ×</button></div>
        <main className="m-main"><Onboarding onPause={() => close(true)} onDone={() => { try { localStorage.setItem("radar.tips.pending", "1"); } catch { /* Optional. */ } window.location.replace("/radar"); }} onError={onError} /></main>
        {error && <p className="m-toast" role="alert" onClick={() => setError("")}>{error}</p>}
      </div>
    </div>
  );
}
