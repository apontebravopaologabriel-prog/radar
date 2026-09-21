"use client";

import { useEffect, useRef } from "react";
import Markdown from "./Markdown";

/** Ventana temporal (como /help en Claude Code): no entra al chat ni a la conversación; Esc la cierra. */
export default function InfoPanel({ title, text, onClose }: { title: string; text: string; onClose: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => { root.current?.focus(); }, []);
  return (
    <div ref={root} className="cfg-picker info-panel" role="dialog" aria-label={title} tabIndex={-1}
      onKeyDown={(e) => { if (e.key === "Escape" || e.key === "q" || e.key === "Enter") { e.preventDefault(); e.stopPropagation(); onClose(); } }}>
      <div className="cfg-picker-title">{title}</div>
      <div className="info-body"><Markdown text={text} /></div>
      <div className="cfg-picker-hint">esc para cerrar · ↑↓ PgUp PgDn desplazan</div>
    </div>
  );
}
