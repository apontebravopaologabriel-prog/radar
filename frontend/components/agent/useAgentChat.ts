"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamChat, type AgentSettings, type ApiMessage, type ConversationInfo, type PendingAction } from "../../lib/mobile-api";

export type Line = { kind: "user" | "assistant" | "tool" | "error" | "local"; text: string };
const SAVE_DELAY_MS = 900;

/** Estado y acciones del chat del agente, compartidos por la app móvil y la ventana de escritorio.
 *  La conversación se guarda en la base local del usuario (no en el navegador). */
export function useAgentChat(onError: (e: unknown) => void) {
  const [history, setHistory] = useState<ApiMessage[]>([]);
  const [lines, setLines] = useState<Line[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [needsSetup, setNeedsSetup] = useState(false);
  const conversationId = useRef<string | null>(null);
  const loaded = useRef(false);
  const abort = useRef<AbortController | null>(null);

  const refreshSettings = useCallback(() => api.agentSettings().then(setSettings).catch(() => undefined), []);

  useEffect(() => {
    api.agentSettings().then(setSettings).catch(onError);
    api.setupStatus().then((st) => setNeedsSetup(!st.complete)).catch(() => undefined);
    // Retoma la conversación más reciente.
    api.conversations().then(async ({ conversations }) => {
      const latest = conversations[0];
      if (latest) {
        const saved = await api.conversation(latest.id);
        conversationId.current = saved.id;
        setHistory(saved.data.history ?? []);
        setLines((saved.data.lines ?? []) as Line[]);
      }
    }).catch(() => undefined).finally(() => { loaded.current = true; });
  }, [onError]);

  // Guardado con retraso: solo cuando hay algo que conservar y ya se cargó el historial.
  useEffect(() => {
    if (!loaded.current || lines.length === 0) return;
    const timer = setTimeout(async () => {
      const firstUser = lines.find((l) => l.kind === "user")?.text ?? "Conversación";
      const title = firstUser.slice(0, 60);
      const data = { history: history.slice(-60), lines: lines.slice(-100) };
      try {
        if (conversationId.current) await api.saveConversation(conversationId.current, title, data);
        else conversationId.current = (await api.createConversation(title, data)).id;
      } catch { /* no interrumpe el chat si no se pudo guardar */ }
    }, SAVE_DELAY_MS);
    return () => clearTimeout(timer);
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
  /** Empieza una conversación nueva (la anterior queda guardada). */
  const reset = useCallback(() => { abort.current?.abort(); conversationId.current = null; setHistory([]); setLines([]); setPending([]); }, []);
  const open = useCallback(async (id: string) => {
    abort.current?.abort();
    const saved = await api.conversation(id);
    conversationId.current = saved.id;
    setHistory(saved.data.history ?? []); setLines((saved.data.lines ?? []) as Line[]); setPending([]);
  }, []);
  /** Borra una conversación (la actual si no se indica). */
  const remove = useCallback(async (id?: string) => {
    const target = id ?? conversationId.current;
    if (target) await api.deleteConversation(target);
    if (!id || id === conversationId.current) reset();
  }, [reset]);
  const list = useCallback(async (): Promise<ConversationInfo[]> => (await api.conversations()).conversations, []);
  const stop = useCallback(() => abort.current?.abort(), []);
  return { lines, pending, busy, settings, needsSetup, send, decide, reset, stop, addLocal, refreshSettings, open, remove, list };
}
