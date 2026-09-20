"use client";

import { useEffect, useRef, useState } from "react";
import type { useAgentChat } from "./useAgentChat";

type Chat = ReturnType<typeof useAgentChat>;
const SUGGESTIONS = ["¿Qué hay nuevo hoy?", "¿Qué skill me conviene aprender?", "Muéstrame mi seguimiento", "¿Cómo se usa Radar?"];
const SETUP_PROMPT = "Ayúdame a configurar Radar";

/** Conversación + tarjetas de confirmación + cuadro de texto. Sin cabecera: la pone quien lo aloja. */
export default function AgentChatPanel({ chat, onSettings }: { chat: Chat; onSettings: () => void }) {
  const [input, setInput] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const { lines, pending, busy, settings, needsSetup, send, decide, stop } = chat;
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [lines, pending]);

  return (
    <div className="m-chat">
      {settings && !settings.ready && (
        <button className="m-callout" onClick={onSettings}>
          <strong>Falta tu clave de API</strong>
          <span>El agente usa tu propia clave (por ejemplo DeepSeek). Se guarda en tu equipo, no en el navegador. Toca para configurar.</span>
        </button>
      )}
      <div className="m-messages" aria-live="polite">
        {lines.length === 0 && (
          <div className="m-suggest">
            {needsSetup && <button className="m-suggest-primary" onClick={() => send(SETUP_PROMPT)}>{SETUP_PROMPT}</button>}
            {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
          </div>
        )}
        {lines.map((line, index) => <div key={index} className={`m-msg m-msg-${line.kind}`}>{line.text}</div>)}
        {pending.map((action) => (
          <div className="m-confirm" key={action.id}>
            <strong>El agente quiere: {action.description}</strong>
            <code>{action.name}({JSON.stringify(action.arguments)})</code>
            <div className="m-actions"><button onClick={() => decide(action, true)}>Aprobar</button><button onClick={() => decide(action, false)}>Rechazar</button></div>
          </div>
        ))}
        {busy && <div className="m-msg m-msg-tool">Pensando…</div>}
        <div ref={bottom} />
      </div>
      <form className="m-compose" onSubmit={(e) => { e.preventDefault(); const text = input; setInput(""); void send(text); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Pregunta sobre ofertas, brechas…" aria-label="Mensaje" maxLength={2000} />
        {busy ? <button type="button" onClick={stop}>Parar</button> : <button type="submit" disabled={!input.trim()}>Enviar</button>}
      </form>
    </div>
  );
}
