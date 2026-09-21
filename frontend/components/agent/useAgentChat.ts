"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamChat, type AgentContext, type AgentSettings, type ApiMessage, type ConversationInfo, type PendingAction } from "../../lib/mobile-api";

export type Line = { kind: "user" | "assistant" | "tool" | "error" | "local"; text: string; durationMs?: number };
const SAVE_DELAY_MS = 900;
/** Peso aproximado del prompt de sistema y las definiciones de herramientas (medido con DeepSeek). */
export const BASE_PROMPT_TOKENS = 2800;

/** Estado y acciones del chat del agente, compartidos por la app móvil y la ventana de escritorio.
 *  La conversación se guarda en la base local del usuario (no en el navegador). */
export type ContextMode = "off" | "selection" | "full";
const CONTEXT_MODES: ContextMode[] = ["off", "selection", "full"];
const CONTEXT_KEY = "radar.agent.contextMode";

/** Recorta el contexto según el modo: «selección» omite las filas de los análisis (lo más caro en tokens). */
export function scopeContext(context: AgentContext | undefined, mode: ContextMode): AgentContext | undefined {
  if (!context || mode === "off") return undefined;
  if (mode === "full") return context;
  const { analysis, ...rest } = context;
  return analysis ? { ...rest, analysis: { ...analysis, windows: analysis.windows.map((w) => ({ ...w, rows: [], sql: "" })), recentQueries: [] } } : rest;
}

export function useAgentChat(onError: (e: unknown) => void, context?: AgentContext) {
  const [contextMode, setContextModeState] = useState<ContextMode>("selection");
  useEffect(() => {
    try { const saved = localStorage.getItem(CONTEXT_KEY) as ContextMode | null; if (saved && CONTEXT_MODES.includes(saved)) setContextModeState(saved); } catch { /* sin almacenamiento */ }
  }, []);
  const setContextMode = useCallback((mode: ContextMode) => {
    setContextModeState(mode);
    try { localStorage.setItem(CONTEXT_KEY, mode); } catch { /* sin almacenamiento */ }
  }, []);
  const [history, setHistory] = useState<ApiMessage[]>([]);
  const [lines, setLines] = useState<Line[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [usage, setUsage] = useState({ context: 0, session: 0, estimated: false });
  const [turn, setTurn] = useState<{ startedAt: number; tokens: number } | null>(null);
  const alwaysAllow = useRef<Set<string>>(new Set());  // herramientas aprobadas «siempre» durante esta sesión
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
    const startedAt = performance.now();
    setTurn({ startedAt: Date.now(), tokens: 0 });
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
          setTurn((t) => t && { ...t, tokens: t.tokens + Math.ceil(event.delta.length / 4) });  // estimación mientras llega el texto
          setLines((prev) => first ? [...prev, { kind: "assistant", text }] : [...prev.slice(0, -1), { kind: "assistant", text }]);
        } else if (event.type === "assistant_message") { push(event.message); current = ""; }
        else if (event.type === "tool_result") { push(event.message); setLines((p) => [...p, { kind: "tool", text: `Consultó ${event.name}` }]); }
        else if (event.type === "usage") setUsage((u) => ({ context: event.prompt_tokens, session: u.session + event.prompt_tokens + event.completion_tokens, estimated: false }));
        else if (event.type === "pending") {
          const auto = event.actions.filter((a) => alwaysAllow.current.has(a.name));
          const manual = event.actions.filter((a) => !alwaysAllow.current.has(a.name));
          setPending(manual);
          if (auto.length) autoApprove.current(auto, manual.length === 0, hist);
        }
        else if (event.type === "error") setLines((p) => [...p, { kind: "error", text: event.message }]);
        else if (event.type === "done" && current) { push({ role: "assistant", content: current }); current = ""; }
      }, abort.current.signal, scopeContext(context, contextMode));
    } catch (error) { if ((error as Error).name !== "AbortError") onError(error); }
    finally {
      const durationMs = Math.max(0, Math.round(performance.now() - startedAt));
      setLines((previous) => {
        const index = [...previous].map((line) => line.kind).lastIndexOf("assistant");
        if (index < 0) return previous;
        return previous.map((line, lineIndex) => lineIndex === index ? { ...line, durationMs } : line);
      });
      setBusy(false); setTurn(null); void refreshSettings();
    }
  }, [context, contextMode, onError, refreshSettings]);

  const send = useCallback(async (text: string) => {
    const clean = text.trim();
    if (!clean || busy) return;
    setLines((p) => [...p, { kind: "user", text: clean }]);
    const next: ApiMessage[] = [...history, { role: "user", content: clean }];
    setHistory(next);
    await run(next);
  }, [busy, history, run]);

  const autoApprove = useRef<(actions: PendingAction[], resume: boolean, base: ApiMessage[]) => void>(() => undefined);
  const decide = useCallback(async (action: PendingAction, approve: boolean, always = false) => {
    if (approve && always) alwaysAllow.current.add(action.name);
    try {
      const res = await api.confirm({ tool_call_id: action.id, name: action.name, arguments: action.arguments, approve });
      const rest = pending.filter((p) => p.id !== action.id);
      setPending(rest);
      setLines((p) => [...p, { kind: "tool", text: `${approve ? "Aprobaste" : "Rechazaste"}${always ? " (siempre en esta sesión)" : ""}: ${action.name}` }]);
      const next = [...history, res.message];
      setHistory(next);
      if (rest.length === 0) await run(next);
    } catch (error) { onError(error); }
  }, [history, pending, run, onError]);
  // Las acciones ya aprobadas «siempre» se confirman solas y el turno continúa.
  autoApprove.current = (actions, resume, base) => {
    void (async () => {
      let next = base;
      try {
        for (const action of actions) {
          const res = await api.confirm({ tool_call_id: action.id, name: action.name, arguments: action.arguments, approve: true });
          next = [...next, res.message];
          setLines((p) => [...p, { kind: "tool", text: `Aprobada automáticamente: ${action.name}` }]);
        }
        setHistory(next);
        if (resume) await run(next);
      } catch (error) { onError(error); }
    })();
  };
  /** Vuelve al último mensaje de la persona (Esc Esc): lo quita de la conversación y devuelve su texto para editarlo. */
  const rewind = useCallback((): string | null => {
    const lastLine = [...lines].map((l) => l.kind).lastIndexOf("user");
    if (lastLine < 0) return null;
    const text = lines[lastLine].text;
    const lastMsg = [...history].map((m, i) => (m.role === "user" && m.content === text ? i : -1)).filter((i) => i >= 0).pop();
    setLines(lines.slice(0, lastLine));
    if (lastMsg !== undefined) setHistory(history.slice(0, lastMsg));
    setPending([]);
    return text;
  }, [history, lines]);

  const addLocal = useCallback((text: string, kind: Line["kind"] = "local") => setLines((p) => [...p, { kind, text }]), []);
  /** Empieza una conversación nueva (la anterior queda guardada). */
  const reset = useCallback(() => { abort.current?.abort(); conversationId.current = null; setHistory([]); setLines([]); setPending([]); setUsage({ context: 0, session: 0, estimated: false }); }, []);
  /** Resume la conversación con el modelo y continúa desde el resumen. Devuelve un texto para mostrar. */
  const compact = useCallback(async (focus = ""): Promise<string> => {
    if (history.length < 2) return "Aún no hay nada que compactar.";
    const before = usage.context;
    const res = await api.compact(history, focus);
    setHistory([
      { role: "user", content: `Resumen de la conversación hasta ahora (compactada):\n${res.summary}` },
      { role: "assistant", content: "Entendido. Continúo desde ese resumen." },
    ]);
    setUsage((u) => ({ context: res.completion_tokens + BASE_PROMPT_TOKENS, session: u.session + res.prompt_tokens + res.completion_tokens, estimated: true }));
    return `Conversación compactada${before ? `: ~${Math.round(before / 100) / 10}k → ~${Math.round((res.completion_tokens + BASE_PROMPT_TOKENS) / 100) / 10}k tokens de contexto` : ""}.\n\n${res.summary}`;
  }, [history, usage.context]);
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
  return { lines, pending, busy, settings, needsSetup, usage, turn, contextMode, setContextMode, rewind, send, decide, reset, stop, addLocal, refreshSettings, open, remove, list, compact };
}
