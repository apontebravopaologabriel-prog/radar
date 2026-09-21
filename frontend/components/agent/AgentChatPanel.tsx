"use client";

import { memo, useEffect, useRef, useState } from "react";
import { api, type AgentContext } from "../../lib/mobile-api";
import { SHORTCUTS, findCommand, matchCommands } from "./commands";
import ConfigPicker from "./ConfigPicker";
import Markdown from "./Markdown";
import ResumePicker from "./ResumePicker";
import RadarMark from "./RadarMark";
import type { useAgentChat } from "./useAgentChat";

type Chat = ReturnType<typeof useAgentChat>;
type LineData = Chat["lines"][number];

const TermLine = memo(function TermLine({ line }: { line: LineData }) {
  return (
    <div className={`term-line term-${line.kind}`}>
      <span className="term-glyph" aria-hidden>{line.kind === "user" ? "❯" : line.kind === "tool" ? "⎿" : line.kind === "error" ? "✕" : line.kind === "local" ? "▸" : <RadarMark />}</span>
      <div className="term-body">{line.kind === "assistant" || line.kind === "local" ? <Markdown text={line.text} /> : line.text}{line.durationMs !== undefined && <small className="term-response-meta">{(line.durationMs / 1000).toFixed(1)} s</small>}</div>
    </div>
  );
});
/** «✻ Analizando… (12 s · ↓1,2k tokens · esc para detener)», como el indicador de Claude Code. */
function Working({ startedAt, tokens }: { startedAt: number; tokens: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(id); }, []);
  const seconds = Math.max(0, Math.round((now - startedAt) / 1000));
  const count = tokens >= 1000 ? `${(tokens / 1000).toFixed(1)}k` : String(tokens);
  return <div className="term-line term-tool"><span className="term-glyph"><RadarMark spinning /></span><div className="term-body">Analizando… <span className="term-dim">({seconds} s{tokens > 0 ? ` · ↓${count} tokens` : ""} · esc para detener)</span></div></div>;
}
const SETUP_PROMPT = "Ayúdame a configurar Radar";
const transcriptOf = (lines: { kind: string; text: string }[]) =>
  lines.map((l) => (l.kind === "user" ? `**❯ ${l.text}**` : l.kind === "tool" ? `> ${l.text}` : l.text)).join("\n\n");

/** Terminal minimal: líneas con prefijo, respuestas en Markdown, comandos con `/` y aprobación con teclado. */
export default function AgentChatPanel({ chat, context, onSettings, dock, onClose }: { chat: Chat; context?: AgentContext; onSettings: () => void; dock?: { pinned: boolean; toggle: () => void }; onClose?: () => void }) {
  const [input, setInput] = useState("");
  const [menuIndex, setMenuIndex] = useState(0);
  const [menuOpen, setMenuOpen] = useState(true);
  const [configMenu, setConfigMenu] = useState<"model" | "effort" | null>(null);
  const [resumeOpen, setResumeOpen] = useState(false);
  const recall = useRef<{ list: string[]; at: number }>({ list: [], at: -1 });
  const bottom = useRef<HTMLDivElement>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const { lines, pending, busy, settings, needsSetup, send, decide, stop, reset, addLocal, refreshSettings, open, remove, list, compact, usage, turn, title, rename: renameChat, contextMode, setContextMode, rewind } = chat;
  const matches = menuOpen ? matchCommands(input) : [];
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [lines, pending, busy]);
  useEffect(() => { setMenuIndex(0); setMenuOpen(true); }, [input]);
  useEffect(() => {
    const el = promptRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;  // crece hasta ~6 líneas
  }, [input]);
  useEffect(() => { if (!configMenu && !resumeOpen) promptRef.current?.focus(); }, [configMenu, resumeOpen]);

  const effortLabel = (value: string) => value === "auto" ? "Auto" : value[0].toUpperCase() + value.slice(1);
  const contextLabel = context?.screen === "analysis" ? "ANÁLISIS" : context?.screen === "cvs" ? "CVs" : context?.mode === "radar" ? `RADAR / ${context.district || "LIMA"} / ${context.radar?.radiusKm ?? 5} KM` : context?.mode === "districts" ? `DISTRITOS / ${context.district || "TODOS"}` : "MAPA / OFERTAS";
  const applyConfig = async (model: string, effort: "auto" | "none" | "low" | "high" | "max") => {
    if (!settings) return;
    try { await api.saveAgentSettings({ provider: settings.provider, model, reasoning_effort: effort }); await refreshSettings(); }
    catch { onSettings(); }
  };

  const lastEsc = useRef(0);
  const lastCtrlC = useRef(0);
  const search = useRef<{ query: string; at: number } | null>(null);
  /** Ctrl+R: recorre hacia atrás los mensajes que contienen lo escrito; repetir pasa al siguiente. */
  const searchHistory = () => {
    const list = recall.current.list;
    if (!list.length) return;
    const state = search.current ?? { query: input, at: list.length };
    for (let i = state.at - 1; i >= 0; i--) {
      if (list[i].toLowerCase().includes(state.query.toLowerCase()) && list[i] !== input) { search.current = { query: state.query, at: i }; setInput(list[i]); return; }
    }
    search.current = null;
  };
  const toggleReadOnly = async () => {
    if (!settings) return;
    try {
      await api.saveAgentSettings({ provider: settings.provider, read_only: !settings.read_only });
      await refreshSettings();
      addLocal(settings.read_only ? "Modo normal: el agente puede proponer cambios (con tu aprobación)." : "Modo solo lectura: el agente solo consulta.");
    } catch { onSettings(); }
  };

  const submit = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    recall.current = { list: [...recall.current.list, text].slice(-50), at: -1 };
    search.current = null;
    setInput("");
    if (text.startsWith("#")) {
      // Atajo de memoria: "# prefiero híbrido" lo recuerda en cada conversación.
      addLocal(text, "user");
      const note = text.replace(/^#+\s*/, "").trim();
      try { const { items } = await import("../../lib/mobile-api").then((m) => m.api.memory()); await import("../../lib/mobile-api").then((m) => m.api.setMemory([...items, note])); addLocal(`Anotado: _${note}_`); }
      catch (error) { addLocal(error instanceof Error ? error.message : "No se pudo guardar.", "error"); }
      return;
    }
    if (!text.startsWith("/")) { await send(text); return; }
    const [head, ...rest] = text.slice(1).split(/\s+/);
    const command = findCommand(head.toLowerCase());
    addLocal(text, "user");
    if (!command) { addLocal(`Comando desconocido: \`/${head}\`. Prueba \`/ayuda\`.`, "error"); return; }
    try {
      const out = await command.run(rest.join(" "), {
        send, reset, refreshSettings, open, remove, list, compact, usage, openConfigMenu: (section = "model") => setConfigMenu(section), openResume: () => setResumeOpen(true), rename: renameChat, title, dock, close: onClose,
        transcript: () => transcriptOf(lines),
        lastAnswer: () => [...lines].reverse().find((l) => l.kind === "assistant" || l.kind === "local")?.text ?? "",
      });
      if (out) addLocal(out);
    } catch (error) { addLocal(error instanceof Error ? error.message : "El comando falló.", "error"); }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (matches.length) {
      if (event.key === "ArrowDown") { event.preventDefault(); setMenuIndex((i) => (i + 1) % matches.length); return; }
      if (event.key === "ArrowUp") { event.preventDefault(); setMenuIndex((i) => (i - 1 + matches.length) % matches.length); return; }
      if (event.key === "Escape") { event.preventDefault(); setMenuOpen(false); return; }
      if (event.key === "Tab" || (event.key === "Enter" && input !== `/${matches[menuIndex].name}`)) {
        event.preventDefault(); const c = matches[menuIndex]; setInput(`/${c.name}${c.args ? " " : ""}`); return;
      }
    }
    if (event.key === "Enter" && event.shiftKey) return;  // salto de línea
    if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (input.endsWith("\\")) { setInput(`${input.slice(0, -1)}\n`); return; }  // «\» + Enter también inserta salto
      void submit(input); return;
    }
    if (event.key === "Escape" && busy) { event.preventDefault(); stop(); return; }
    if (input === "" && pending.length && ["y", "n", "1", "2", "3"].includes(event.key)) {
      event.preventDefault();
      void decide(pending[0], event.key !== "n" && event.key !== "3", event.key === "2"); return;
    }
    if (input === "" && event.key === "?") { event.preventDefault(); addLocal(SHORTCUTS); return; }
    if (event.key === "Tab" && event.shiftKey) { event.preventDefault(); void toggleReadOnly(); return; }
    if (event.ctrlKey && event.key.toLowerCase() === "k") { event.preventDefault(); setContextMode(contextMode === "off" ? "selection" : contextMode === "selection" ? "full" : "off"); return; }
    if (event.ctrlKey && event.key.toLowerCase() === "r") { event.preventDefault(); searchHistory(); return; }
    if (event.ctrlKey && event.key.toLowerCase() === "c" && (event.currentTarget.selectionStart === event.currentTarget.selectionEnd)) {
      event.preventDefault();
      if (busy) { stop(); return; }
      if (input) { setInput(""); return; }
      const now = Date.now();
      if (now - lastCtrlC.current < 1500 && onClose) { onClose(); return; }
      lastCtrlC.current = now; addLocal("Pulsa Ctrl+C otra vez para salir."); return;
    }
    if (event.key === "Escape" && !busy && !input) {
      const now = Date.now();
      if (now - lastEsc.current < 600) { lastEsc.current = 0; const text = rewind(); if (text !== null) setInput(text); return; }
      lastEsc.current = now; return;
    }
    if (event.key === "ArrowUp" && !input) {
      const r = recall.current; const at = r.at < 0 ? r.list.length - 1 : Math.max(r.at - 1, 0);
      if (r.list[at] !== undefined) { event.preventDefault(); r.at = at; setInput(r.list[at]); }
    }
  };

  return (
    <div className="m-chat term">
      {settings && !settings.ready && (
        <button className="m-callout" onClick={onSettings}>
          <strong>Falta tu clave de API</strong>
          <span>Los comandos con <code>/</code> funcionan sin clave; para conversar con el agente hace falta la tuya (por ejemplo DeepSeek). Toca para configurar.</span>
        </button>
      )}
      <div className="term-log" aria-live="polite">
        {lines.length === 0 && (
          <div className="term-welcome">
            <span className="term-dim">escribe <b>/</b> para comandos · <b>?</b> atajos{needsSetup ? " · " : ""}{needsSetup && <button onClick={() => send(SETUP_PROMPT)}>/init</button>}</span>
          </div>
        )}
        {lines.map((line, index) => <TermLine key={index} line={line} />)}
        {pending.map((action) => (
          <div className="term-confirm" key={action.id}>
            <div><b>Acción propuesta:</b> {action.description}</div>
            <code>{action.name}({JSON.stringify(action.arguments)})</code>
            <div className="m-actions">
              <button onClick={() => decide(action, true)}>[1] Sí</button>
              <button onClick={() => decide(action, true, true)}>[2] Sí, y no preguntar más esta sesión</button>
              <button onClick={() => decide(action, false)}>[3] No</button>
            </div>
          </div>
        ))}
        {busy && <Working startedAt={turn?.startedAt ?? Date.now()} tokens={turn?.tokens ?? 0} />}
        <div ref={bottom} />
      </div>
      {matches.length > 0 && (
        <ul className="term-menu" role="listbox" aria-label="Comandos">
          {matches.map((c, i) => (
            <li key={c.name} role="option" aria-selected={i === menuIndex} className={i === menuIndex ? "on" : ""}
              onMouseDown={(e) => { e.preventDefault(); setInput(`/${c.name}${c.args ? " " : ""}`); }}>
              <span>/{c.name}{c.args ? ` ${c.args}` : ""}</span><small>{c.hint}</small>
            </li>
          ))}
        </ul>
      )}
      <form className="term-prompt" onSubmit={(e) => { e.preventDefault(); void submit(input); }}>
        <span className="term-glyph" aria-hidden>❯</span>
        <textarea ref={promptRef} rows={1} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown} placeholder="pregunta o / para comandos · Shift+Enter nueva línea" aria-label="Mensaje" maxLength={2000} autoComplete="off" spellCheck={false} />
        {busy && <button type="button" onClick={stop}>esc</button>}
      </form>
      {resumeOpen && <ResumePicker onOpen={open} onDelete={(id) => remove(id)} onClose={() => setResumeOpen(false)} />}
      {configMenu && settings && <ConfigPicker settings={settings} focus={configMenu} onApply={applyConfig} onClose={() => setConfigMenu(null)} />}
      <div className="term-footer">
        <span>
          {busy ? "esc detener" : "? atajos"}
          {settings?.read_only ? " · ⏸ lectura" : ""}
          {" · "}
          <button type="button" className="term-context-toggle" title="Contexto de pantalla que recibe el agente (Ctrl+K): apagado → selección → completo"
            onClick={() => setContextMode(contextMode === "off" ? "selection" : contextMode === "selection" ? "full" : "off")}>
            {contextMode === "off" ? "○ sin contexto" : `◉ ${contextMode === "full" ? "completo" : "selección"}`}
          </button>
          {contextMode !== "off" && <> · {contextLabel.toLowerCase()}{(context?.districtJobs ?? context?.visibleCount) !== undefined ? ` · ${context?.districtJobs ?? context?.visibleCount}` : ""}</>}
        </span>
        {settings?.ready ? <span>{settings.model} · {effortLabel(settings.reasoning_effort)} · {usage.context && settings ? Math.min(100, Math.round((usage.context / settings.context_window) * 100)) : 0}% · mes {Math.round((settings.tokens_used_this_month / Math.max(settings.monthly_token_cap, 1)) * 100)}%</span> : <span>sin configurar</span>}
      </div>
    </div>
  );
}
