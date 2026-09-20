"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/mobile-api";
import "./mobile.css";
import Onboarding from "./Onboarding";

const KEY = "radar.firstrun.dismissed.v1";

/** Primer inicio en escritorio: si no hay perfil, ofrece las preguntas de bienvenida en una ventana. */
export default function FirstRun() {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const onError = useCallback((e: unknown) => setError(e instanceof Error ? e.message : "Error desconocido"), []);

  useEffect(() => {
    let dismissed = false;
    try { dismissed = localStorage.getItem(KEY) === "1"; } catch { /* sin almacenamiento */ }
    if (dismissed) return;
    api.setupStatus().then((s) => setOpen(!s.steps.find((x) => x.id === "profile")?.done)).catch(() => undefined);
  }, []);

  const close = (remember: boolean) => {
    if (remember) { try { localStorage.setItem(KEY, "1"); } catch { /* sin almacenamiento */ } }
    setOpen(false);
  };
  if (!open) return null;
  return (
    <div className="firstrun-backdrop" role="dialog" aria-modal="true" aria-label="Bienvenida a Radar">
      <div className="m-app firstrun-window">
        <div className="firstrun-bar"><span>[INICIO]</span><button type="button" onClick={() => close(true)}>Omitir por ahora ×</button></div>
        <main className="m-main"><Onboarding onDone={() => { close(false); window.location.reload(); }} onError={onError} /></main>
        {error && <p className="m-toast" role="alert" onClick={() => setError("")}>{error}</p>}
      </div>
    </div>
  );
}
