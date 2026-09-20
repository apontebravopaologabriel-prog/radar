"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AgentSettings } from "../../lib/mobile-api";
import "../mobile/mobile.css";
import "./agent-window.css";
import RadarMark from "./RadarMark";

// El cuerpo del chat solo se descarga cuando el agente está activado y la ventana se abre.
const AgentWindowBody = dynamic(() => import("./AgentWindowBody"), { ssr: false });

type Geometry = { x: number; y: number; w: number; h: number };
type Mode = "float" | "pinned";
const KEY = "radar.agent.window.v2";
const MIN_W = 320;
const MIN_H = 300;
const PIN_MIN = 320;
const PIN_MAX = 760;

function defaults(): Geometry {
  const w = 400; const h = 540;
  return { x: Math.max(16, window.innerWidth - w - 24), y: Math.max(16, window.innerHeight - h - 24), w, h };
}
function clamp(g: Geometry): Geometry {
  const w = Math.min(Math.max(g.w, MIN_W), window.innerWidth - 16);
  const h = Math.min(Math.max(g.h, MIN_H), window.innerHeight - 16);
  return { w, h, x: Math.min(Math.max(g.x, 8), window.innerWidth - w - 8), y: Math.min(Math.max(g.y, 8), window.innerHeight - h - 8) };
}

/** Lanzador del agente en escritorio: ventana flotante o panel fijado a la derecha. Apagado, solo queda el acceso a Ajustes. */
export default function AgentDock() {
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [mode, setMode] = useState<Mode>("float");
  const [pinWidth, setPinWidth] = useState(420);
  const [geo, setGeo] = useState<Geometry | null>(null);
  const drag = useRef<{ dx: number; dy: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const enabled = settings?.enabled === true;
  const pinned = enabled && open && mode === "pinned";

  useEffect(() => { api.agentSettings().then(setSettings).catch(() => setSettings(null)); }, []);
  useEffect(() => {
    let saved: Partial<Geometry & { open: boolean; minimized: boolean; mode: Mode; pinWidth: number }> = {};
    try { saved = JSON.parse(localStorage.getItem(KEY) ?? "{}"); } catch { /* sin almacenamiento */ }
    const base = defaults();
    setGeo(clamp({ x: saved.x ?? base.x, y: saved.y ?? base.y, w: saved.w ?? base.w, h: saved.h ?? base.h }));
    setOpen(saved.open === true || window.location.hash === "#agente");
    setMinimized(saved.minimized === true);
    setMode(saved.mode === "pinned" ? "pinned" : "float");
    setPinWidth(Math.min(Math.max(saved.pinWidth ?? 420, PIN_MIN), PIN_MAX));
  }, []);
  useEffect(() => {
    if (!geo) return;
    try { localStorage.setItem(KEY, JSON.stringify({ ...geo, open, minimized, mode, pinWidth })); } catch { /* sin almacenamiento */ }
  }, [geo, open, minimized, mode, pinWidth]);

  // Al fijar el panel, el mapa cede ese ancho y se le avisa del cambio de tamaño.
  useEffect(() => {
    document.documentElement.style.setProperty("--agent-dock-w", pinned ? `${pinWidth}px` : "0px");
    const frame = requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
    return () => cancelAnimationFrame(frame);
  }, [pinned, pinWidth]);
  useEffect(() => () => { document.documentElement.style.setProperty("--agent-dock-w", "0px"); }, []);

  const toggle = useCallback(() => { setOpen((v) => !v); setMinimized(false); }, []);
  const toggleMode = useCallback(() => setMode((m) => (m === "float" ? "pinned" : "float")), []);
  useEffect(() => {
    if (!enabled) return;
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "j") { event.preventDefault(); toggle(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, toggle]);

  // Guarda el tamaño que el usuario elige con el tirador nativo de redimensionar (ventana flotante).
  useEffect(() => {
    const el = box.current;
    if (!el || !open || minimized || mode !== "float" || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      const { width, height } = el.getBoundingClientRect();
      setGeo((g) => g && (Math.abs(g.w - width) > 1 || Math.abs(g.h - height) > 1) ? clamp({ ...g, w: width, h: height }) : g);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [open, minimized, enabled, mode]);

  const onDown = (event: React.PointerEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest("button") || mode !== "float" || !geo) return;
    drag.current = { dx: event.clientX - geo.x, dy: event.clientY - geo.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onMove = (event: React.PointerEvent<HTMLElement>) => {
    const d = drag.current;
    if (d && geo) setGeo(clamp({ ...geo, x: event.clientX - d.dx, y: event.clientY - d.dy }));
  };
  const onUp = () => { drag.current = null; };
  const onError = useCallback(() => undefined, []);
  const dock = { pinned: mode === "pinned", toggle: toggleMode };

  // Arrastre del borde izquierdo del panel fijado para cambiar su ancho.
  const onResizeDown = (event: React.PointerEvent<HTMLElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const move = (e: PointerEvent) => setPinWidth(Math.min(Math.max(window.innerWidth - e.clientX, PIN_MIN), PIN_MAX));
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const titlebar = (
    <header className="agent-titlebar" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
      <span><RadarMark size={12} /> radar</span>
      <div>
        <button type="button" onClick={toggleMode} aria-label={mode === "pinned" ? "Volver a ventana" : "Fijar a la derecha"} title={mode === "pinned" ? "Ventana flotante" : "Fijar a la derecha"}>{mode === "pinned" ? "❐" : "⇥"}</button>
        {mode === "float" && <button type="button" onClick={() => setMinimized(!minimized)} aria-label={minimized ? "Restaurar" : "Minimizar"}>{minimized ? "▢" : "–"}</button>}
        <button type="button" onClick={() => setOpen(false)} aria-label="Cerrar">×</button>
      </div>
    </header>
  );

  return (
    <>
      <div className="agent-dock">
        {enabled && <button type="button" onClick={toggle} aria-pressed={open} title="Agente (Ctrl+J)">{open ? "× agente" : "> agente"}</button>}
        <a href="/ajustes" title="Ajustes" aria-label="Ajustes">⚙</a>
      </div>
      {enabled && open && mode === "float" && geo && (
        <div ref={box} className={`agent-window m-app ${minimized ? "is-min" : ""}`} role="dialog" aria-label="Agente de Radar"
          style={{ left: geo.x, top: geo.y, width: geo.w, height: minimized ? undefined : geo.h }}>
          {titlebar}
          {!minimized && <AgentWindowBody onError={onError} dock={dock} onClose={() => setOpen(false)} />}
        </div>
      )}
      {enabled && open && mode === "pinned" && (
        <aside className="agent-pinned m-app" style={{ width: pinWidth }} aria-label="Agente de Radar">
          <div className="agent-pinned-resize" onPointerDown={onResizeDown} role="separator" aria-orientation="vertical" aria-label="Ajustar ancho" />
          {titlebar}
          <AgentWindowBody onError={onError} dock={dock} onClose={() => setOpen(false)} />
        </aside>
      )}
    </>
  );
}
