"use client";

import { useEffect, useRef, useState } from "react";
import { COMMANDS, matchCommands } from "./commands";
import Markdown from "./Markdown";
import RadarMark from "./RadarMark";
import type { useAgentChat } from "./useAgentChat";

type Chat = ReturnType<typeof useAgentChat>;
const SETUP_PROMPT = "Ayúdame a configurar Radar";

/** Terminal minimal: líneas con prefijo, respuestas en Markdown, comandos con `/` y aprobación con teclado. */
export default function AgentChatPanel({ chat, onSettings }: { chat: Chat; onSettings: () => void }) {
  const [input, setInput] = useState("");
  const [menuIndex, setMenuIndex] = useState(0);
  const [menuOpen, setMenuOpen] = useState(true);
  const recall = useRef<{ list: string[]; at: number }>({ list: [], at: -1 });
  const bottom = useRef<HTMLDivElement>(null);
  const { lines, pending, busy, settings, needsSetup, send, decide, stop, reset, addLocal, refreshSettings } = chat;
  const matches = menuOpen ? matchCommands(input) : [];
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [lines, pending, busy]);
  useEffect(() => { setMenuIndex(0); setMenuOpen(true); }, [input]);

  const submit = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    recall.current = { list: [...recall.current.list, text].slice(-50), at: -1 };
    setInput("");
    if (!text.startsWith("/")) { await send(text); return; }
    const [head, ...rest] = text.slice(1).split(/\s+/);
    const command = COMMANDS.find((c) => c.name === head.toLowerCase());
    addLocal(text, "user");
    if (!command) { addLocal(`Comando desconocido: \`/${head}\`. Prueba \`/ayuda\`.`, "error"); return; }
    try {
      const out = await command.run(rest.join(" "), { send, reset, refreshSettings });
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
            <div><RadarMark size={16} /> <b>Agente de Radar</b></div>
            <p>Escribe una pregunta, o <code>/</code> para ver los comandos.</p>
            <div className="term-suggest">
              {needsSetup && <button onClick={() => send(SETUP_PROMPT)}>/ {SETUP_PROMPT}</button>}
              {["/hoy", "/mapa", "/skills", "/ayuda"].map((c) => <button key={c} onClick={() => submit(c)}>{c}</button>)}
            </div>
          </div>
        )}
        {lines.map((line, index) => (
          <div key={index} className={`term-line term-${line.kind}`}>
            <span className="term-glyph" aria-hidden>{line.kind === "user" ? "❯" : line.kind === "tool" ? "⎿" : line.kind === "error" ? "✕" : line.kind === "local" ? "▸" : <RadarMark />}</span>
            <div className="term-body">{line.kind === "assistant" || line.kind === "local" ? <Markdown text={line.text} /> : line.text}</div>
          </div>
        ))}
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
    </div>
  );
}
