"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamChat, type AgentContext, type Mention, type AgentSettings, type ApiContentPart, type ApiMessage, type ConversationInfo, type PendingAction } from "../../lib/mobile-api";

export type PastedBlock = { id: number; lines: number; chars: number; text: string };
export type AttachedImage = { id: number; dataUrl: string; width: number; height: number; name?: string };

export type Line = { kind: "user" | "assistant" | "tool" | "error" | "local"; text: string; durationMs?: number;
  /** Llamada a herramienta: resumen de una línea del resultado y el resultado recortado (Ctrl+O lo expande). */
  summary?: string; detail?: string;
  /** Razonamiento del modelo (Ctrl+O o clic lo despliega) y bloques adjuntos al estilo Claude Code. */
  reasoning?: string; pastedBlocks?: PastedBlock[]; images?: AttachedImage[] };

/** En modo auto solo se aprueban solas estas acciones (seguimiento personal); las de sistema, CV o datos siempre piden confirmación. */
const AUTO_SAFE = new Set(["favorite_job", "track_job_application", "import_job_url", "remember_user", "record_career_event"]);
const DETAIL_MAX = 800;
const shortArgs = (raw: string) => {
  try {
    const args = JSON.parse(raw || "{}") as Record<string, unknown>;
    return Object.entries(args).map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ").slice(0, 72);
  } catch { return ""; }
};
/** Una línea legible del resultado de una herramienta: error, conteo de filas o número de campos. */
const summarizeResult = (content: string | ApiContentPart[] | null): { summary: string; detail: string } => {
  const rawContent = typeof content === "string" ? content : null;
  let inner: unknown = rawContent;
  try { const parsed = JSON.parse(rawContent ?? "null") as Record<string, unknown> | null; inner = parsed && "datos_externos_no_confiables" in parsed ? parsed.datos_externos_no_confiables : parsed; } catch { /* texto */ }
  const detail = (typeof inner === "string" ? inner : JSON.stringify(inner, null, 1) ?? "").slice(0, DETAIL_MAX);
  if (inner && typeof inner === "object" && !Array.isArray(inner)) {
    const obj = inner as Record<string, unknown>;
    if (typeof obj.error === "string") return { summary: `error: ${obj.error.slice(0, 80)}`, detail };
    const list = Object.entries(obj).find(([, v]) => Array.isArray(v)) as [string, unknown[]] | undefined;
    if (list) return { summary: `${list[1].length} ${list[0]}${typeof obj.total === "number" ? ` de ${obj.total}` : ""}`, detail };
    return { summary: `${Object.keys(obj).length} campos`, detail };
  }
  return { summary: "listo", detail };
};
const SAVE_DELAY_MS = 900;
/** Qué conversación está activa, para que sobreviva a que la ventana del agente se cierre y se reabra
 *  (se desmonta y el estado en memoria se pierde). "new" = recién limpiada, aún sin guardar. */
const ACTIVE_CONVERSATION_KEY = "radar.agent.activeConversation";
const readActiveConversation = (): string | null => { try { return localStorage.getItem(ACTIVE_CONVERSATION_KEY); } catch { return null; } };
const writeActiveConversation = (value: string | null) => {
  try { if (value) localStorage.setItem(ACTIVE_CONVERSATION_KEY, value); else localStorage.removeItem(ACTIVE_CONVERSATION_KEY); } catch { /* sin almacenamiento */ }
};
/** Peso aproximado del prompt de sistema y las definiciones de herramientas (medido con DeepSeek). */
export const BASE_PROMPT_TOKENS = 2800;

/** Estado y acciones del chat del agente, compartidos por la app móvil y la ventana de escritorio.
 *  La conversación se guarda en la base local del usuario (no en el navegador). */
export type ContextMode = "off" | "selection" | "full";
const CONTEXT_MODES: ContextMode[] = ["off", "selection", "full"];
const CONTEXT_KEY = "radar.agent.contextMode";
const TITLE_MAX = 60;
/** Título automático: el primer mensaje de la persona. */
/** Últimos 60 mensajes, empezando siempre en un mensaje de la persona y sin guardar imágenes base64 ni reasoning pesado en disco. */
function trimHistory(history: ApiMessage[]): ApiMessage[] {
  const tail = history.slice(-60);
  const first = tail.findIndex((m) => m.role === "user");
  if (first < 0) return [];
  return tail.slice(first).map((m) => {
    const clean: ApiMessage = { role: m.role, content: m.content };
    if (m.tool_call_id) clean.tool_call_id = m.tool_call_id;
    if (m.tool_calls) clean.tool_calls = m.tool_calls;
    if (Array.isArray(m.content)) {
      const texts = m.content.map((p) => (p.type === "text" ? p.text : "[Imagen adjunta]")).join("\n");
      clean.content = texts;
    }
    return clean;
  });
}

function trimLinesForStorage(lines: Line[]): Line[] {
  return lines.slice(-100).map((l) => (l.images?.length ? { ...l, images: l.images.map((img) => ({ ...img, dataUrl: "" })) } : l));
}

const autoTitle = (lines: { kind: string; text: string }[]) => (lines.find((l) => l.kind === "user")?.text ?? "").slice(0, TITLE_MAX);

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
  const historyRef = useRef<ApiMessage[]>([]);
  historyRef.current = history;
  const [lines, setLines] = useState<Line[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const pendingRef = useRef<PendingAction[]>([]);
  pendingRef.current = pending;
  const [deciding, setDeciding] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [usage, setUsage] = useState({ context: 0, session: 0, cacheHit: 0, estimated: false });
  const usageRef = useRef(usage);
  usageRef.current = usage;  // el turno lee el tamaño real del último prompt sin volver a crear `run`
  const [planMode, setPlanModeState] = useState(false);
  const planRef = useRef(false);  // lectura síncrona: aprobar el plan y enviar ocurren en el mismo instante
  const [autoMode, setAutoModeState] = useState(false);  // modo auto: aprueba solas las acciones de bajo riesgo
  const autoRef = useRef(false);
  const setPlanMode = useCallback((value: boolean) => {
    planRef.current = value; setPlanModeState(value);
    if (value) { autoRef.current = false; setAutoModeState(false); }
  }, []);
  const setAutoMode = useCallback((value: boolean) => {
    autoRef.current = value; setAutoModeState(value);
    if (value) { planRef.current = false; setPlanModeState(false); }
  }, []);  // modo plan: el agente investiga y propone, sin escribir
  const [planReady, setPlanReady] = useState(false);  // hay un plan esperando aprobación
  const [customTitle, setCustomTitle] = useState<string | null>(null);  // título puesto a mano; null = automático
  const [turn, setTurn] = useState<{ startedAt: number; tokens: number; phase?: "thinking" | "writing" } | null>(null);
  const alwaysAllow = useRef<Set<string>>(new Set());  // herramientas aprobadas «siempre» durante esta sesión
  const conversationId = useRef<string | null>(null);
  const loaded = useRef(false);
  const abort = useRef<AbortController | null>(null);

  const reportError = useCallback((error: unknown) => {
    const msg = error instanceof Error ? error.message : "Error inesperado en el agente.";
    setLines((p) => [...p, { kind: "error", text: msg }]);
    onError(error);
  }, [onError]);

  const refreshSettings = useCallback(() => api.agentSettings().then(setSettings).catch(() => undefined), []);

  useEffect(() => {
    api.agentSettings().then(setSettings).catch(onError);
    api.setupStatus().then((st) => setNeedsSetup(!st.complete)).catch(() => undefined);
    // Retoma la conversación activa (la que dejó la sesión anterior de esta ventana), no siempre "la más reciente":
    // si el usuario la limpió con /clear, debe seguir en blanco aunque cierre y reabra la ventana del agente.
    const active = readActiveConversation();
    if (active === "new") { loaded.current = true; return; }
    (async () => {
      // Si había una conversación activa marcada, esa; si no (primera vez), la más reciente guardada.
      let id = active;
      if (!id) { const { conversations } = await api.conversations(); id = conversations[0]?.id ?? null; }
      if (!id) return;
      const saved = await api.conversation(id);
      conversationId.current = saved.id;
      writeActiveConversation(saved.id);
      setHistory(saved.data.history ?? []);
      setLines((saved.data.lines ?? []) as Line[]);
      setPending((saved.data.pending ?? []) as PendingAction[]);
      setCustomTitle(saved.title !== autoTitle((saved.data.lines ?? []) as Line[]) ? saved.title : null);
    })().catch(() => undefined).finally(() => { loaded.current = true; });
  }, [onError]);

  // Guardado con retraso: solo cuando hay algo que conservar y ya se cargó el historial.
  useEffect(() => {
    if (!loaded.current || lines.length === 0) return;
    const timer = setTimeout(async () => {
      const title = customTitle ?? (autoTitle(lines) || "Conversación");
      const data = { history: trimHistory(history), lines: trimLinesForStorage(lines), pending: pending.length ? pending : undefined };
      try {
        if (conversationId.current) await api.saveConversation(conversationId.current, title, data);
        else { conversationId.current = (await api.createConversation(title, data)).id; writeActiveConversation(conversationId.current); }
      } catch { /* no interrumpe el chat si no se pudo guardar */ }
    }, SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [history, lines, pending, customTitle]);

  /** Ejecuta un turno con el historial dado. */
  const run = useCallback(async (base: ApiMessage[], mentions: Mention[] = []) => {
    setBusy(true); setPending([]); pendingRef.current = []; setPlanReady(false);
    const planning = planRef.current;
    let failed = false;
    const startedAt = performance.now();
    setTurn({ startedAt: Date.now(), tokens: 0 });
    let current = "";
    let currentReasoning = "";
    let hist = base;
    const toolArgs = new Map<string, string>();  // id de la llamada -> argumentos, para mostrar «herramienta(args)»
    abort.current = new AbortController();
    const push = (message: ApiMessage) => { hist = [...hist, message]; historyRef.current = hist; setHistory(hist); };
    try {
      await streamChat(base, (event) => {
        if (event.type === "reasoning") {
          currentReasoning += event.delta;
          setTurn((t) => t && { ...t, phase: "thinking", tokens: t.tokens + Math.ceil(event.delta.length / 4) });
        } else if (event.type === "text") {
          const first = current === "";
          current += event.delta;
          const text = current;
          const reasoning = currentReasoning || undefined;
          setTurn((t) => t && { ...t, phase: "writing", tokens: t.tokens + Math.ceil(event.delta.length / 4) });  // estimación mientras llega el texto
          setLines((prev) => first ? [...prev, { kind: "assistant", text, reasoning }] : [...prev.slice(0, -1), { kind: "assistant", text, reasoning }]);
        } else if (event.type === "assistant_message") {
          for (const call of event.message.tool_calls ?? []) toolArgs.set(call.id, call.function.arguments);
          push(event.message); current = ""; currentReasoning = "";
        }
        else if (event.type === "tool_result") {
          push(event.message);
          const { summary, detail } = summarizeResult(event.message.content);
          setLines((p) => [...p, { kind: "tool", text: `${event.name}(${shortArgs(toolArgs.get(event.message.tool_call_id ?? "") ?? "")})`, summary, detail }]);
        }
        else if (event.type === "usage") setUsage((u) => ({ context: event.prompt_tokens, session: u.session + event.prompt_tokens + event.completion_tokens, cacheHit: event.cache_hit_tokens ?? 0, estimated: false }));
        else if (event.type === "compacted") {
          hist = event.history; historyRef.current = hist; setHistory(hist);
          setUsage((u) => ({ ...u, context: BASE_PROMPT_TOKENS + Math.ceil(event.summary.length / 4), cacheHit: 0, estimated: true }));
          const hints = event.memory_candidates.map((c) => `\n  # ${c}`).join("");
          setLines((p) => [...p, { kind: "local", text: `Contexto compactado automáticamente (~${Math.round(event.before_tokens / 100) / 10}k tokens antes).\n\n${event.summary}${hints ? `\n\nSi quieres que lo recuerde, copia una línea con #:${hints}` : ""}` }]);
        }
        else if (event.type === "notice") setLines((p) => [...p, { kind: "local", text: event.message }]);
        else if (event.type === "pending") {
          const isAuto = (a: PendingAction) => alwaysAllow.current.has(a.name) || (autoRef.current && AUTO_SAFE.has(a.name));
          const auto = event.actions.filter(isAuto);
          const manual = event.actions.filter((a) => !isAuto(a));
          pendingRef.current = manual;
          setPending(manual);
          if (auto.length) autoApprove.current(auto, manual.length === 0, hist);
        }
        else if (event.type === "error") { failed = true; setLines((p) => [...p, { kind: "error", text: event.message }]); }
        else if (event.type === "done" && current) { push({ role: "assistant", content: current }); current = ""; currentReasoning = ""; }
      }, abort.current.signal, mentions.length ? { ...scopeContext(context, contextMode), mentions } : scopeContext(context, contextMode), planning, usageRef.current.context);
    } catch (error) { if ((error as Error).name !== "AbortError") reportError(error); }
    finally {
      const durationMs = Math.max(0, Math.round(performance.now() - startedAt));
      setLines((previous) => {
        const index = [...previous].map((line) => line.kind).lastIndexOf("assistant");
        if (index < 0) return previous;
        return previous.map((line, lineIndex) => lineIndex === index ? { ...line, durationMs } : line);
      });
      setBusy(false); setTurn(null); void refreshSettings();
      if (planning && !failed) setPlanReady(true);
    }
  }, [context, contextMode, reportError, refreshSettings]);

  const send = useCallback(async (text: string, mentions: Mention[] = [], attachments?: { pastedBlocks?: PastedBlock[]; images?: AttachedImage[] }) => {
    const clean = text.trim();
    const pastedBlocks = attachments?.pastedBlocks ?? [];
    const images = attachments?.images ?? [];
    if ((!clean && !pastedBlocks.length && !images.length) || busy) return;
    // Si había tarjetas de confirmación pendientes y la persona escribe otro mensaje, cerrarlas como canceladas para no dejar llamadas huérfanas.
    let baseHistory = historyRef.current;
    if (pendingRef.current.length > 0) {
      const cancelled: ApiMessage[] = pendingRef.current.map((a) => ({
        role: "tool",
        tool_call_id: a.id,
        content: JSON.stringify({ datos_externos_no_confiables: { cancelado_por_el_usuario: true } }),
      }));
      baseHistory = [...baseHistory, ...cancelled];
      pendingRef.current = [];
      setPending([]);
    }
    const displayText = clean || (images.length ? "(imagen adjunta)" : `(texto pegado · ${pastedBlocks.reduce((acc, b) => acc + b.lines, 0)} líneas)`);
    setLines((p) => [...p, { kind: "user", text: displayText, pastedBlocks: pastedBlocks.length ? pastedBlocks : undefined, images: images.length ? images : undefined }]);
    const pastedSection = pastedBlocks
      .map((b) => `\n\n--- [Texto pegado #${b.id} (${b.lines} líneas)] ---\n${b.text}`)
      .join("");
    const fullText = `${clean}${pastedSection}`.trim() || "Analiza esta imagen.";
    const content: string | ApiContentPart[] = images.length
      ? [
          { type: "text", text: fullText },
          ...images.map((img): ApiContentPart => ({ type: "image_url", image_url: { url: img.dataUrl } })),
        ]
      : fullText;
    const next: ApiMessage[] = [...baseHistory, { role: "user", content }];
    historyRef.current = next;
    setHistory(next);
    await run(next, mentions);
  }, [busy, run]);

  const autoApprove = useRef<(actions: PendingAction[], resume: boolean, base: ApiMessage[]) => void>(() => undefined);
  const decide = useCallback(async (action: PendingAction, approve: boolean, always = false) => {
    if (deciding) return;
    if (approve && always) alwaysAllow.current.add(action.name);
    // Si eligió «siempre en esta sesión», aprobar también las demás acciones pendientes de la misma herramienta.
    const currentPending = pendingRef.current;
    const targets = approve && always
      ? currentPending.filter((p) => p.id === action.id || p.name === action.name)
      : [action];
    const targetIds = new Set(targets.map((t) => t.id));
    setDeciding(targets.length > 1 ? "all" : action.id);
    try {
      let next = historyRef.current;
      for (const target of targets) {
        const res = await api.confirm({ tool_call_id: target.id, name: target.name, arguments: target.arguments, approve });
        if (approve && typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("radar:jobs-changed", { detail: { name: target.name, arguments: target.arguments } }));
        }
        next = [...next, res.message];
        if (approve) {
          const { summary, detail } = summarizeResult(res.message.content);
          setLines((p) => [...p, { kind: "tool", text: `Aprobaste${always ? " (siempre en esta sesión)" : ""}: ${target.name}`, summary, detail }]);
        } else {
          setLines((p) => [...p, { kind: "tool", text: `Rechazaste: ${target.name}` }]);
        }
      }
      const rest = pendingRef.current.filter((p) => !targetIds.has(p.id));
      pendingRef.current = rest;
      setPending(rest);
      historyRef.current = next;
      setHistory(next);
      setDeciding(null);
      if (rest.length === 0) await run(next);
    } catch (error) {
      setDeciding(null);
      reportError(error);
    }
  }, [deciding, run, reportError]);

  const decideAll = useCallback(async (approve: boolean) => {
    if (deciding || pendingRef.current.length === 0) return;
    const targets = [...pendingRef.current];
    setDeciding("all");
    try {
      let next = historyRef.current;
      for (const target of targets) {
        const res = await api.confirm({ tool_call_id: target.id, name: target.name, arguments: target.arguments, approve });
        if (approve && typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("radar:jobs-changed", { detail: { name: target.name, arguments: target.arguments } }));
        }
        next = [...next, res.message];
        if (approve) {
          const { summary, detail } = summarizeResult(res.message.content);
          setLines((p) => [...p, { kind: "tool", text: `Aprobaste: ${target.name}`, summary, detail }]);
        } else {
          setLines((p) => [...p, { kind: "tool", text: `Rechazaste: ${target.name}` }]);
        }
      }
      pendingRef.current = [];
      setPending([]);
      historyRef.current = next;
      setHistory(next);
      setDeciding(null);
      await run(next);
    } catch (error) {
      setDeciding(null);
      reportError(error);
    }
  }, [deciding, run, reportError]);

  // Las acciones ya aprobadas «siempre» se confirman solas y el turno continúa.
  autoApprove.current = (actions, resume, base) => {
    void (async () => {
      let next = base;
      try {
        for (const action of actions) {
          const res = await api.confirm({ tool_call_id: action.id, name: action.name, arguments: action.arguments, approve: true });
          if (typeof window !== "undefined") {
            window.dispatchEvent(new CustomEvent("radar:jobs-changed", { detail: { name: action.name, arguments: action.arguments } }));
          }
          next = [...next, res.message];
          const { summary, detail } = summarizeResult(res.message.content);
          setLines((p) => [...p, { kind: "tool", text: `Aprobada automáticamente: ${action.name}`, summary, detail }]);
        }
        historyRef.current = next;
        setHistory(next);
        if (resume) await run(next);
      } catch (error) { reportError(error); }
    })();
  };
  /** Vuelve al último mensaje de la persona (Esc Esc): lo quita de la conversación y devuelve su texto para editarlo. */
  const rewind = useCallback((): string | null => {
    const lastLine = [...lines].map((l) => l.kind).lastIndexOf("user");
    if (lastLine < 0) return null;
    const text = lines[lastLine].text;
    const lastMsg = [...history].map((m, i) => (m.role === "user" ? i : -1)).filter((i) => i >= 0).pop();
    setLines(lines.slice(0, lastLine));
    if (lastMsg !== undefined) {
      const sliced = history.slice(0, lastMsg);
      historyRef.current = sliced;
      setHistory(sliced);
    }
    pendingRef.current = [];
    setPending([]);
    return text;
  }, [history, lines]);

  const addLocal = useCallback((text: string, kind: Line["kind"] = "local") => setLines((p) => [...p, { kind, text }]), []);
  /** Empieza una conversación nueva (la anterior queda guardada). */
  const reset = useCallback(() => { abort.current?.abort(); conversationId.current = null; writeActiveConversation("new"); setPlanReady(false); setCustomTitle(null); historyRef.current = []; setHistory([]); setLines([]); pendingRef.current = []; setPending([]); setDeciding(null); setUsage({ context: 0, session: 0, cacheHit: 0, estimated: false }); }, []);
  /** Resume la conversación con el modelo y continúa desde el resumen. Devuelve un texto para mostrar. */
  const compact = useCallback(async (focus = ""): Promise<string> => {
    if (history.length < 2) return "Aún no hay nada que compactar.";
    const before = usage.context;
    const res = await api.compact(history, focus);
    const compacted: ApiMessage[] = [
      { role: "user", content: `Resumen de la conversación hasta ahora (compactada):\n${res.summary}` },
      { role: "assistant", content: "Entendido. Continúo desde ese resumen." },
    ];
    historyRef.current = compacted;
    setHistory(compacted);
    setUsage((u) => ({ context: res.completion_tokens + BASE_PROMPT_TOKENS, session: u.session + res.prompt_tokens + res.completion_tokens, cacheHit: 0, estimated: true }));
    return `Conversación compactada${before ? `: ~${Math.round(before / 100) / 10}k → ~${Math.round((res.completion_tokens + BASE_PROMPT_TOKENS) / 100) / 10}k tokens de contexto` : ""}.\n\n${res.summary}`;
  }, [history, usage.context]);
  const open = useCallback(async (id: string) => {
    abort.current?.abort();
    const saved = await api.conversation(id);
    conversationId.current = saved.id;
    writeActiveConversation(saved.id);
    historyRef.current = saved.data.history ?? [];
    setHistory(saved.data.history ?? []);
    setLines((saved.data.lines ?? []) as Line[]);
    pendingRef.current = (saved.data.pending ?? []) as PendingAction[];
    setPending((saved.data.pending ?? []) as PendingAction[]);
    setDeciding(null);
    setCustomTitle(saved.title !== autoTitle((saved.data.lines ?? []) as Line[]) ? saved.title : null);
  }, []);
  /** Borra una conversación (la actual si no se indica). */
  const remove = useCallback(async (id?: string) => {
    const target = id ?? conversationId.current;
    if (target) await api.deleteConversation(target);
    if (!id || id === conversationId.current) reset();
  }, [reset]);
  const list = useCallback(async (): Promise<ConversationInfo[]> => (await api.conversations()).conversations, []);
  /** Renombra la conversación actual; un texto vacío vuelve al título automático. */
  const rename = useCallback((value: string) => {
    const clean = value.replace(/\s+/g, " ").trim().slice(0, TITLE_MAX);
    setCustomTitle(clean || null);
  }, []);
  /** Aprueba el plan: sale del modo plan y pide ejecutarlo (cada escritura sigue pidiendo confirmación). */
  const approvePlan = useCallback(async () => {
    setPlanMode(false); setPlanReady(false);
    await send("Apruebo el plan. Ejecútalo paso a paso; confirmaré cada acción que modifique datos.");
  }, [send, setPlanMode]);
  const title = customTitle ?? autoTitle(lines);
  const stop = useCallback(() => abort.current?.abort(), []);
  return { lines, pending, deciding, busy, settings, needsSetup, usage, turn, title, rename, planMode, setPlanMode, autoMode, setAutoMode, planReady, setPlanReady, approvePlan, contextMode, setContextMode, rewind, send, decide, decideAll, reset, stop, addLocal, refreshSettings, open, remove, list, compact };
}
