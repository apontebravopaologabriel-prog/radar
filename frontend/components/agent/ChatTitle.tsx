"use client";

import { useEffect, useRef, useState } from "react";

/** Título de la conversación en la barra superior: clic para renombrar (Enter guarda, Esc cancela). */
export default function ChatTitle({ title, onRename }: { title: string; onRename: (value: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { if (editing) { setDraft(title); input.current?.select(); } }, [editing]); // eslint-disable-line react-hooks/exhaustive-deps
  const stop = (event: React.SyntheticEvent) => event.stopPropagation();  // no iniciar el arrastre de la ventana
  const finish = (save: boolean) => { if (save && draft.trim() !== title) onRename(draft); setEditing(false); };

  if (!title) return <em className="chat-title chat-title-empty">nueva conversación</em>;
  if (editing) {
    return <input ref={input} className="chat-title chat-title-input" value={draft} maxLength={60} autoFocus aria-label="Título de la conversación"
      onChange={(e) => setDraft(e.target.value)} onPointerDown={stop}
      onKeyDown={(e) => { e.stopPropagation(); if (e.key === "Enter") finish(true); else if (e.key === "Escape") finish(false); }}
      onBlur={() => finish(true)} />;
  }
  return <button type="button" className="chat-title" onPointerDown={stop} onClick={() => setEditing(true)} title="Clic para renombrar (o /rename)">{title}<i aria-hidden> ✎</i></button>;
}
