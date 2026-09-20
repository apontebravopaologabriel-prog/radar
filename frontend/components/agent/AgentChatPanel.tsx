"use client";

import { memo, useEffect, useRef, useState } from "react";
import { api, type AgentContext } from "../../lib/mobile-api";
import { findCommand, matchCommands } from "./commands";
import Markdown from "./Markdown";
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
const SETUP_PROMPT = "Ayúdame a configurar Radar";
const transcriptOf = (lines: { kind: string; text: string }[]) =>
  lines.map((l) => (l.kind === "user" ? `**❯ ${l.text}**` : l.kind === "tool" ? `> ${l.text}` : l.text)).join("\n\n");

/** Terminal minimal: líneas con prefijo, respuestas en Markdown, comandos con `/` y aprobación con teclado. */
export default function AgentChatPanel({ chat, context, onSettings, dock, onClose }: { chat: Chat; context?: AgentContext; onSettings: () => void; dock?: { pinned: boolean; toggle: () => void }; onClose?: () => void }) {
  const [input, setInput] = useState("");
  const [menuIndex, setMenuIndex] = useState(0);
  const [menuOpen, setMenuOpen] = useState(true);
  const [configMenu, setConfigMenu] = useState<"model" | "effort" | null>(null);
  const [configIndex, setConfigIndex] = useState(0);
  const recall = useRef<{ list: string[]; at: number }>({ list: [], at: -1 });
  const bottom = useRef<HTMLDivElement>(null);
  const configMenuRef = useRef<HTMLDivElement>(null);
  const { lines, pending, busy, settings, needsSetup, send, decide, stop, reset, addLocal, refreshSettings, open, remove, list, compact, usage, contextMode, setContextMode } = chat;
  const matches = menuOpen ? matchCommands(input) : [];
  const provider = settings?.providers[settings.provider];
  const modelOptions = provider?.models?.length ? provider.models : settings?.model ? [settings.model] : [];
  const modelLabel = (value: string) => provider?.model_names?.[value] ?? value;
  const effortOptions = ["auto", ...(provider?.reasoning_efforts ?? [])].filter((value, index, values) => values.indexOf(value) === index);
  const configOptions = configMenu === "model" ? modelOptions : effortOptions;
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [lines, pending, busy]);
  useEffect(() => { setMenuIndex(0); setMenuOpen(true); }, [input]);
  useEffect(() => { setConfigIndex(0); }, [configMenu]);
  useEffect(() => { if (configMenu) configMenuRef.current?.focus(); }, [configMenu]);

  const effortLabel = (value: string) => value === "auto" ? "Auto" : value[0].toUpperCase() + value.slice(1);
  const contextLabel = context?.screen === "analysis" ? "ANÁLISIS" : context?.screen === "cvs" ? "CVs" : context?.mode === "radar" ? `RADAR / ${context.district || "LIMA"} / ${context.radar?.radiusKm ?? 5} KM` : context?.mode === "districts" ? `DISTRITOS / ${context.district || "TODOS"}` : "MAPA / OFERTAS";
  const selectConfig = async (value: string) => {
    if (!settings || !configMenu || busy) return;
    try {
      if (configMenu === "model") await api.saveAgentSettings({ provider: settings.provider, model: value });
      else await api.saveAgentSettings({ provider: settings.provider, reasoning_effort: value as "auto" | "none" | "low" | "high" | "max" });
      await refreshSettings();
      setConfigMenu(null);
    } catch { onSettings(); }
  };

  const onConfigKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") { event.preventDefault(); setConfigMenu(null); return; }
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault(); setConfigMenu(event.key === "ArrowLeft" ? "model" : "effort"); return;
    }
    if (!configOptions.length) return;
    if (event.key === "ArrowDown") { event.preventDefault(); setConfigIndex((index) => (index + 1) % configOptions.length); }
    if (event.key === "ArrowUp") { event.preventDefault(); setConfigIndex((index) => (index - 1 + configOptions.length) % configOptions.length); }
    if (event.key === "Enter") { event.preventDefault(); void selectConfig(configOptions[configIndex]); }
  };

  const submit = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    recall.current = { list: [...recall.current.list, text].slice(-50), at: -1 };
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
        send, reset, refreshSettings, open, remove, list, compact, usage, openConfigMenu: (section = "model") => setConfigMenu(section), dock, close: onClose,
        transcript: () => transcriptOf(lines),
        lastAnswer: () => [...lines].reverse().find((l) => l.kind === "assistant" || l.kind === "local")?.text ?? "",
      });
      if (out) addLocal(out);
    } catch (error) { addLocal(error instanceof Error ? error.message : "El comando falló.", "error"); }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (matches.length) {
      if (event.key === "ArrowDown") { event.preventDefault(); setMenuIndex((i) => (i + 1) % matches.length); return; }
      if (event.key === "ArrowUp") { event.preventDefault(); setMenuIndex((i) => (i - 1 + matches.length) % matches.length); return; }
      if (event.key === "Escape") { event.preventDefault(); setMenuOpen(false); return; }
      if (event.key === "Tab" || (event.key === "Enter" && input !== `/${matches[menuIndex].name}`)) {
        event.preventDefault(); const c = matches[menuIndex]; setInput(`/${c.name}${c.args ? " " : ""}`); return;
      }
    }
    if (event.key === "Escape" && busy) { event.preventDefault(); stop(); return; }
    if (input === "" && pending.length && (event.key === "y" || event.key === "n")) {
      event.preventDefault(); void decide(pending[0], event.key === "y"); return;
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
            <div><RadarMark size={16} /> <b>radar</b> <span className="term-dim">agente</span></div>
            <p className="term-dim">Pregunta lo que quieras sobre tus ofertas, o escribe / para comandos.</p>
            <div className="term-suggest">
              {needsSetup && <button onClick={() => send(SETUP_PROMPT)}>/init</button>}
              {["/today", "/map", "/skills", "/context", "/help"].map((c) => <button key={c} onClick={() => submit(c)}>{c}</button>)}
            </div>
          </div>
        )}
        {lines.map((line, index) => <TermLine key={index} line={line} />)}
        {pending.map((action) => (
          <div className="term-confirm" key={action.id}>
            <div><b>Acción propuesta:</b> {action.description}</div>
            <code>{action.name}({JSON.stringify(action.arguments)})</code>
            <div className="m-actions"><button onClick={() => decide(action, true)}>[y] Aprobar</button><button onClick={() => decide(action, false)}>[n] Rechazar</button></div>
          </div>
        ))}
        {busy && <div className="term-line term-tool"><span className="term-glyph"><RadarMark spinning /></span><div className="term-body">trabajando…</div></div>}
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
        <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown} placeholder="pregunta o / para comandos" aria-label="Mensaje" maxLength={2000} autoComplete="off" spellCheck={false} />
        {busy && <button type="button" onClick={stop}>esc</button>}
      </form>
      {configMenu && settings && <div ref={configMenuRef} className="term-config-menu" role="dialog" aria-label="Configuración del agente" onKeyDown={onConfigKeyDown} tabIndex={-1}>
        <div className="term-config-tabs">
          <button type="button" className={configMenu === "model" ? "on" : ""} onClick={() => setConfigMenu("model")}>Modelo</button>
          {effortOptions.length > 1 && <button type="button" className={configMenu === "effort" ? "on" : ""} onClick={() => setConfigMenu("effort")}>Effort</button>}
          <span className="term-config-hint">↑↓ elegir · Enter aplicar · Esc cerrar</span>
        </div>
        <div className="term-config-options" role="listbox" aria-label={configMenu === "model" ? "Modelos" : "Esfuerzo de razonamiento"}>
          {configOptions.map((option, index) => <button type="button" role="option" aria-selected={index === configIndex} className={index === configIndex ? "on" : ""} key={option} onMouseEnter={() => setConfigIndex(index)} onClick={() => void selectConfig(option)}>
            <span>{configMenu === "effort" ? effortLabel(option) : modelLabel(option)}</span>
            {(configMenu === "model" ? option === settings.model : option === settings.reasoning_effort) && <b>actual</b>}
          </button>)}
        </div>
      </div>}
      <div className="term-context" title="Contexto de navegación enviado al agente. Pulsa para cambiar: apagado → selección → completo (incluye filas de análisis)">
        <button type="button" className="term-context-toggle" onClick={() => setContextMode(contextMode === "off" ? "selection" : contextMode === "selection" ? "full" : "off")}>
          CONTEXTO · {contextMode === "off" ? "APAGADO" : contextMode === "selection" ? "SELECCIÓN" : "COMPLETO"}
        </button>
        {contextMode !== "off" && <> · {contextLabel}{context?.visibleCount !== undefined ? ` · ${context.visibleCount} ofertas` : ""}</>}
      </div>
      <div className="term-footer">
        <span>{busy ? "esc detener" : "/ commands · # memory · ↑ history"}</span>
        {settings?.ready ? <span>{settings.model} · {effortLabel(settings.reasoning_effort)} · ctx {usage.context && settings ? Math.min(100, Math.round((usage.context / settings.context_window) * 100)) : 0}% · mes {Math.round((settings.tokens_used_this_month / Math.max(settings.monthly_token_cap, 1)) * 100)}%{settings.read_only ? " · lectura" : ""}</span> : <span>sin configurar</span>}
      </div>
    </div>
  );
}
