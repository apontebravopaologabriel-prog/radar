"use client";

import { useEffect, useRef, useState } from "react";
import { api, streamChat, type AgentSettings, type ApiMessage, type PendingAction } from "../../lib/mobile-api";

type Line = { kind: "user" | "assistant" | "tool" | "error"; text: string };
const STORE = "radar.chat.v1";
const SUGGESTIONS = ["¿Qué hay nuevo hoy?", "¿Qué skill me conviene aprender?", "Muéstrame mi seguimiento"];

function load(): { history: ApiMessage[]; lines: Line[] } {
  try { return JSON.parse(localStorage.getItem(STORE) ?? "") as { history: ApiMessage[]; lines: Line[] }; } catch { return { history: [], lines: [] }; }
}

export default function AgentView({ onSettings, onError }: { onSettings: () => void; onError: (e: unknown) => void }) {
  const [history, setHistory] = useState<ApiMessage[]>([]);
  const [lines, setLines] = useState<Line[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => { const s = load(); setHistory(s.history); setLines(s.lines); api.agentSettings().then(setSettings).catch(onError); }, [onError]);
  useEffect(() => {
    try { localStorage.setItem(STORE, JSON.stringify({ history: history.slice(-40), lines: lines.slice(-60) })); } catch { /* sin almacenamiento */ }
    bottom.current?.scrollIntoView({ block: "end" });
  }, [history, lines]);

  /** Ejecuta un turno con el historial dado; devuelve el historial ampliado. */
  const run = async (base: ApiMessage[]) => {
    setBusy(true); setPending([]);
    let current = "";
    let hist = base;
    abort.current = new AbortController();
    const push = (message: ApiMessage) => { hist = [...hist, message]; setHistory(hist); };
    try {
      await streamChat(base, (event) => {
        if (event.type === "text") {
          const first = current === "";
          current += event.delta;
          const text = current;
          setLines((prev) => first ? [...prev, { kind: "assistant", text }] : [...prev.slice(0, -1), { kind: "assistant", text }]);
        } else if (event.type === "assistant_message") { push(event.message); current = ""; }
        else if (event.type === "tool_result") { push(event.message); setLines((p) => [...p, { kind: "tool", text: `Consultó ${event.name}` }]); }
        else if (event.type === "pending") setPending(event.actions);
        else if (event.type === "error") setLines((p) => [...p, { kind: "error", text: event.message }]);
        else if (event.type === "done" && current) { push({ role: "assistant", content: current }); current = ""; }
      }, abort.current.signal);
    } catch (error) { if ((error as Error).name !== "AbortError") onError(error); }
    finally { setBusy(false); api.agentSettings().then(setSettings).catch(() => undefined); }
  };

  const send = async (text: string) => {
    const clean = text.trim();
    if (!clean || busy) return;
    setInput("");
    setLines((p) => [...p, { kind: "user", text: clean }]);
    const next: ApiMessage[] = [...history, { role: "user", content: clean }];
    setHistory(next);
    await run(next);
  };

  const decide = async (action: PendingAction, approve: boolean) => {
    try {
      const res = await api.confirm({ tool_call_id: action.id, name: action.name, arguments: action.arguments, approve });
      const rest = pending.filter((p) => p.id !== action.id);
      setPending(rest);
      setLines((p) => [...p, { kind: "tool", text: `${approve ? "Aprobaste" : "Rechazaste"}: ${action.name}` }]);
      const next = [...history, res.message];
      setHistory(next);
      if (rest.length === 0) await run(next);
    } catch (error) { onError(error); }
  };

  const reset = () => { abort.current?.abort(); setHistory([]); setLines([]); setPending([]); };
  const cap = settings?.monthly_token_cap ?? 0;
  const used = settings?.tokens_used_this_month ?? 0;

  return (
    <div className="m-chat">
      <header className="m-head m-head-row">
        <div><h1>Agente</h1>{settings && <p>{settings.ready ? `${settings.model} · ${Math.round((used / Math.max(cap, 1)) * 100)}% del tope mensual` : "Sin configurar"}</p>}</div>
        {lines.length > 0 && <button className="m-link" onClick={reset}>Nueva</button>}
      </header>
      {settings && !settings.ready && (
        <button className="m-callout" onClick={onSettings}>
          <strong>Falta tu clave de API</strong>
          <span>El agente usa tu propia clave (por ejemplo DeepSeek). Se guarda en tu equipo, no en el navegador. Toca para configurar.</span>
        </button>
      )}
      <div className="m-messages" aria-live="polite">
        {lines.length === 0 && (
          <div className="m-suggest">{SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}</div>
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
      <form className="m-compose" onSubmit={(e) => { e.preventDefault(); void send(input); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Pregunta sobre ofertas, brechas…" aria-label="Mensaje" maxLength={2000} />
        {busy ? <button type="button" onClick={() => abort.current?.abort()}>Parar</button> : <button type="submit" disabled={!input.trim()}>Enviar</button>}
      </form>
    </div>
  );
}
