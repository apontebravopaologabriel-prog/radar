"use client";
import { useEffect, useRef, useState } from "react";
import { fetchProcesses, PROCESS_EVENT, type ProcessInput, type ProcessItem } from "../lib/processes-api";
import ProcessForm from "./ProcessForm";
import "./processes.css";
export default function ProcessContactDialog() {
  const [draft, setDraft] = useState<ProcessInput | ProcessItem | null>(null);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const panel = useRef<HTMLDivElement>(null);
  const close = () => { generation.current++; setDraft(null); setError(""); };
  useEffect(() => {
    let active = true;
    async function open(event: Event) {
      const next = (event as CustomEvent<ProcessInput>).detail;
      const request = ++generation.current; setError("");
      try { const existing = (await fetchProcesses()).find((p) => p.job_id === next.job_id); if (active && request === generation.current) setDraft(existing ?? next); }
      catch { if (active && request === generation.current) { setDraft(next); setError("No se pudo comprobar si ya existe. Guardar verificará los duplicados."); } }
    }
    window.addEventListener(PROCESS_EVENT, open); return () => { active = false; window.removeEventListener(PROCESS_EVENT, open); };
  }, []);
  useEffect(() => {
    if (!draft) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLInputElement>("input")?.focus();
    return () => previous?.focus();
  }, [draft]);
  if (!draft) return null;
  return <div className="process-dialog" onKeyDown={(e) => {
    if (e.key === "Escape") { e.stopPropagation(); close(); }
    if (e.key === "Tab") {
      const nodes = Array.from(panel.current?.querySelectorAll<HTMLElement>("input,select,textarea,button") ?? []).filter((el) => !el.matches(":disabled"));
      if (e.shiftKey && document.activeElement === nodes[0]) { e.preventDefault(); nodes.at(-1)?.focus(); }
      else if (!e.shiftKey && document.activeElement === nodes.at(-1)) { e.preventDefault(); nodes[0]?.focus(); }
    }
  }}><div ref={panel} role="dialog" aria-modal="true" aria-label="Me contactaron"><p>Registra este proceso cuando hayas recibido una respuesta.</p>{error && <p role="alert">{error}</p>}<ProcessForm initial={draft} id={"id" in draft ? draft.id : undefined} onSaved={close} onCancel={close} /></div></div>;
}
