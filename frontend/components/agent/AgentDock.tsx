"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type AgentContext, type AgentSettings } from "../../lib/mobile-api";
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
export default function AgentDock({ context }: { context?: AgentContext }) {
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [mode, setMode] = useState<Mode>("float");
  const [pinWidth, setPinWidth] = useState(420);
  const [geo, setGeo] = useState<Geometry | null>(null);
  const drag = useRef<{ dx: number; dy: number; x: number; y: number } | null>(null);
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
    let timer: ReturnType<typeof setTimeout> | null = null;
    const observer = new ResizeObserver(() => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        const { width, height } = el.getBoundingClientRect();
        setGeo((g) => g && (Math.abs(g.w - width) > 1 || Math.abs(g.h - height) > 1) ? clamp({ ...g, w: width, h: height }) : g);
      }, 200);
    });
    observer.observe(el);
    return () => { observer.disconnect(); if (timer) clearTimeout(timer); };
  }, [open, minimized, enabled, mode]);

  // Arrastre: mientras se mueve solo se cambia `transform` (compositor, sin relayout ni re-render de React);
  // la posición se guarda en el estado una sola vez al soltar.
  const frame = useRef<number | null>(null);
  const onDown = (event: React.PointerEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest("button") || mode !== "float" || !geo) return;
    drag.current = { dx: event.clientX - geo.x, dy: event.clientY - geo.y, x: geo.x, y: geo.y };
    if (box.current) box.current.style.willChange = "transform";
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onMove = (event: React.PointerEvent<HTMLElement>) => {
    const d = drag.current;
    if (!d || !geo) return;
    const next = clamp({ ...geo, x: event.clientX - d.dx, y: event.clientY - d.dy });
    d.x = next.x; d.y = next.y;
    if (frame.current === null) {
      frame.current = requestAnimationFrame(() => {
        frame.current = null;
        if (box.current && drag.current) box.current.style.transform = `translate3d(${drag.current.x - geo.x}px, ${drag.current.y - geo.y}px, 0)`;
      });
    }
  };
  const onUp = () => {
    const d = drag.current;
    drag.current = null;
    if (frame.current !== null) { cancelAnimationFrame(frame.current); frame.current = null; }
    if (box.current) { box.current.style.transform = ""; box.current.style.willChange = ""; }
    if (d && geo && (d.x !== geo.x || d.y !== geo.y)) setGeo({ ...geo, x: d.x, y: d.y });
  };
  const onError = useCallback(() => undefined, []);
  const dock = useMemo(() => ({ pinned: mode === "pinned", toggle: toggleMode }), [mode, toggleMode]);
  const closeAgent = useCallback(() => setOpen(false), []);
  const [titleSlot, setTitleSlot] = useState<HTMLElement | null>(null);

  // Arrastre del borde izquierdo del panel fijado para cambiar su ancho.
  // Durante el gesto solo cambia el ancho del panel (posición fija, no afecta al resto de la página);
  // el mapa y la barra lateral se reajustan una sola vez al soltar.
  const aside = useRef<HTMLElement>(null);
  const onResizeDown = (event: React.PointerEvent<HTMLElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    let width = pinWidth;
    let raf: number | null = null;
    const move = (e: PointerEvent) => {
      width = Math.min(Math.max(window.innerWidth - e.clientX, PIN_MIN), PIN_MAX);
      if (raf === null) raf = requestAnimationFrame(() => { raf = null; if (aside.current) aside.current.style.width = `${width}px`; });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (raf !== null) cancelAnimationFrame(raf);
      setPinWidth(width);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const titlebar = (
    <header className="agent-titlebar" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
      <span className="agent-title"><RadarMark size={12} /> radar<b className="agent-title-slot" ref={setTitleSlot} /></span>
      <div>
        <button type="button" onClick={toggleMode} aria-label={mode === "pinned" ? "Volver a ventana" : "Fijar a la derecha"} title={mode === "pinned" ? "Ventana flotante" : "Fijar a la derecha"}>{mode === "pinned" ? "❐" : "⇥"}</button>
        {mode === "float" && <button type="button" onClick={() => setMinimized(!minimized)} aria-label={minimized ? "Restaurar" : "Minimizar"}>{minimized ? "▢" : "–"}</button>}
        <button type="button" onClick={() => setOpen(false)} aria-label="Cerrar">×</button>
      </div>
    </header>
  );

  return (
    <>
      <div className="agent-dock is-autohide" aria-label="Controles de Radar">
        {enabled && <button className="agent-launch" type="button" onClick={toggle} aria-pressed={open} aria-label={open ? "Cerrar agente" : "Abrir agente"} title={`${open ? "Cerrar" : "Abrir"} agente (Ctrl+J)`}><RadarMark size={16} spinning={open} /></button>}
        <a href="/ajustes" title="Ajustes" aria-label="Ajustes">⚙</a>
      </div>
      {enabled && open && mode === "float" && geo && (
        <div ref={box} className={`agent-window m-app ${minimized ? "is-min" : ""}`} role="dialog" aria-label="Agente de Radar"
          style={{ left: geo.x, top: geo.y, width: geo.w, height: minimized ? undefined : geo.h }}>
          {titlebar}
          {!minimized && <AgentWindowBody onError={onError} dock={dock} onClose={closeAgent} context={context} titleSlot={titleSlot} />}
        </div>
      )}
      {enabled && open && mode === "pinned" && (
        <aside ref={aside} className="agent-pinned m-app" style={{ width: pinWidth }} aria-label="Agente de Radar">
          <div className="agent-pinned-resize" onPointerDown={onResizeDown} role="separator" aria-orientation="vertical" aria-label="Ajustar ancho" />
          {titlebar}
          <AgentWindowBody onError={onError} dock={dock} onClose={closeAgent} context={context} titleSlot={titleSlot} />
        </aside>
      )}
    </>
  );
}
