"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamChat, type AgentSettings, type ApiMessage, type PendingAction } from "../../lib/mobile-api";

export type Line = { kind: "user" | "assistant" | "tool" | "error" | "local"; text: string };
const STORE = "radar.chat.v1";

function restore(): { history: ApiMessage[]; lines: Line[] } {
  try { return JSON.parse(localStorage.getItem(STORE) ?? "") as { history: ApiMessage[]; lines: Line[] }; } catch { return { history: [], lines: [] }; }
}

/** Estado y acciones del chat del agente, compartidos por la app móvil y la ventana de escritorio. */
export function useAgentChat(onError: (e: unknown) => void) {
  const [history, setHistory] = useState<ApiMessage[]>([]);
  const [lines, setLines] = useState<Line[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [needsSetup, setNeedsSetup] = useState(false);
  const abort = useRef<AbortController | null>(null);

  const refreshSettings = useCallback(() => api.agentSettings().then(setSettings).catch(() => undefined), []);
  useEffect(() => {
    const saved = restore();
    setHistory(saved.history); setLines(saved.lines);
    api.agentSettings().then(setSettings).catch(onError);
    api.setupStatus().then((st) => setNeedsSetup(!st.complete)).catch(() => undefined);
  }, [onError]);
  useEffect(() => {
    try { localStorage.setItem(STORE, JSON.stringify({ history: history.slice(-40), lines: lines.slice(-60) })); } catch { /* sin almacenamiento */ }
  }, [history, lines]);

  /** Ejecuta un turno con el historial dado. */
  const run = useCallback(async (base: ApiMessage[]) => {
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
    finally { setBusy(false); void refreshSettings(); }
  }, [onError, refreshSettings]);

  const send = useCallback(async (text: string) => {
    const clean = text.trim();
    if (!clean || busy) return;
    setLines((p) => [...p, { kind: "user", text: clean }]);
    const next: ApiMessage[] = [...history, { role: "user", content: clean }];
    setHistory(next);
    await run(next);
  }, [busy, history, run]);

  const decide = useCallback(async (action: PendingAction, approve: boolean) => {
    try {
      const res = await api.confirm({ tool_call_id: action.id, name: action.name, arguments: action.arguments, approve });
      const rest = pending.filter((p) => p.id !== action.id);
      setPending(rest);
      setLines((p) => [...p, { kind: "tool", text: `${approve ? "Aprobaste" : "Rechazaste"}: ${action.name}` }]);
      const next = [...history, res.message];
      setHistory(next);
      if (rest.length === 0) await run(next);
    } catch (error) { onError(error); }
  }, [history, pending, run, onError]);

  const addLocal = useCallback((text: string, kind: Line["kind"] = "local") => setLines((p) => [...p, { kind, text }]), []);
  const reset = useCallback(() => { abort.current?.abort(); setHistory([]); setLines([]); setPending([]); }, []);
  const stop = useCallback(() => abort.current?.abort(), []);
  return { lines, pending, busy, settings, needsSetup, send, decide, reset, stop, addLocal, refreshSettings };
}
