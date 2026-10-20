"use client";

import { memo, useEffect, useRef, useState } from "react";
import { api, type AgentContext, type AgentSettings, type Doctor, type Mention } from "../../lib/mobile-api";
import { SHORTCUTS, findCommand, matchCommands } from "./commands";
import ConfigPicker from "./ConfigPicker";
import Markdown from "./Markdown";
import InfoPanel from "./InfoPanel";
import ResumePicker from "./ResumePicker";
import RadarMark from "./RadarMark";
import type { AttachedImage, PastedBlock, useAgentChat } from "./useAgentChat";

type Chat = ReturnType<typeof useAgentChat>;
type LineData = Chat["lines"][number];

const PASTE_COLLAPSE_MIN_LINES = 5;
const PASTE_COLLAPSE_MIN_CHARS = 350;
const MAX_IMAGES_PER_TURN = 3;

async function compressImageFile(file: File): Promise<{ dataUrl: string; width: number; height: number; name: string }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("No se pudo leer la imagen."));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("Formato de imagen no válido."));
      img.onload = () => {
        const maxSide = 1440;
        let width = img.naturalWidth || img.width || 800;
        let height = img.naturalHeight || img.height || 600;
        if (width > maxSide || height > maxSide) {
          if (width >= height) {
            height = Math.round((height * maxSide) / width);
            width = maxSide;
          } else {
            width = Math.round((width * maxSide) / height);
            height = maxSide;
          }
        }
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("No se pudo procesar la imagen."));
          return;
        }
        ctx.drawImage(img, 0, 0, width, height);
        let dataUrl = canvas.toDataURL("image/webp", 0.82);
        if (!dataUrl.startsWith("data:image/webp")) {
          dataUrl = canvas.toDataURL("image/jpeg", 0.82);
        }
        resolve({ dataUrl, width, height, name: file.name || "captura" });
      };
      img.src = String(reader.result);
    };
    reader.readAsDataURL(file);
  });
}

const TermLine = memo(function TermLine({ line, expanded, streaming }: { line: LineData; expanded: boolean; streaming: boolean }) {
  const [openPasteIds, setOpenPasteIds] = useState<number[]>([]);
  const [openImageIds, setOpenImageIds] = useState<number[]>([]);
  const [openReasoning, setOpenReasoning] = useState(false);
  const [openDetail, setOpenDetail] = useState(false);

  if (line.kind === "tool" && line.summary !== undefined) {  // llamada a herramienta: ⏺ nombre(args) / ⎿ resumen (clic o Ctrl+O expande)
    const showDetail = Boolean(line.detail && (expanded || openDetail));
    return (
      <div className={`term-line term-tool term-call${line.summary.startsWith("error") ? " is-error" : ""}`}>
        <span className="term-glyph" aria-hidden>⏺</span>
        <div className="term-body">
          <div className="term-call-head">{line.text}</div>
          <div
            className={`term-call-result${line.detail ? " is-expandable" : ""}`}
            onClick={line.detail ? () => setOpenDetail((v) => !v) : undefined}
          >
            ⎿ {line.summary}{line.detail && !showDetail ? <span className="term-dim"> (clic o ctrl+o)</span> : null}
          </div>
          {showDetail && line.detail && <pre className="term-call-detail">{line.detail}</pre>}
        </div>
      </div>
    );
  }
  const showReasoning = Boolean(line.reasoning && (expanded || openReasoning));
  return (
    <div className={`term-line term-${line.kind}${streaming ? " is-streaming" : ""}`}>
      <span className="term-glyph" aria-hidden>{line.kind === "user" ? "❯" : line.kind === "tool" ? "⎿" : line.kind === "error" ? "✕" : line.kind === "local" ? "▸" : <RadarMark />}</span>
      <div className="term-body">
        {line.kind === "assistant" && line.reasoning && (
          <div className="term-reasoning-box">
            <button type="button" className="term-chip-btn term-reasoning-toggle" onClick={() => setOpenReasoning((v) => !v)}>
              💭 Razonamiento (~{Math.max(1, Math.ceil(line.reasoning.length / 4))} tok · {showReasoning ? "ocultar" : "ctrl+o"})
            </button>
            {showReasoning && <pre className="term-call-detail">{line.reasoning}</pre>}
          </div>
        )}
        {line.kind === "assistant" || line.kind === "local" ? <Markdown text={line.text} /> : line.text}
        {line.kind === "user" && (line.pastedBlocks?.length || line.images?.length) ? (
          <div className="term-attachments-log">
            {line.pastedBlocks?.map((b) => {
              const isOpen = expanded || openPasteIds.includes(b.id);
              return (
                <div key={`p-${b.id}`} className="term-attach-item">
                  <button
                    type="button"
                    className="term-chip-btn"
                    onClick={() => setOpenPasteIds((prev) => (prev.includes(b.id) ? prev.filter((x) => x !== b.id) : [...prev, b.id]))}
                  >
                    [Pasted text #{b.id} +{b.lines} lines]
                  </button>
                  {isOpen && <pre className="term-call-detail">{b.text}</pre>}
                </div>
              );
            })}
            {line.images?.map((img) => {
              const isOpen = openImageIds.includes(img.id);
              return (
                <div key={`i-${img.id}`} className="term-attach-item">
                  <button
                    type="button"
                    className="term-chip-btn"
                    disabled={!img.dataUrl}
                    onClick={() => setOpenImageIds((prev) => (prev.includes(img.id) ? prev.filter((x) => x !== img.id) : [...prev, img.id]))}
                  >
                    [Image #{img.id} · {img.width}×{img.height}]
                  </button>
                  {isOpen && img.dataUrl && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={img.dataUrl} alt={`Imagen #${img.id}`} className="term-image-preview" />
                  )}
                </div>
              );
            })}
          </div>
        ) : null}
        {line.durationMs !== undefined && <small className="term-response-meta">{(line.durationMs / 1000).toFixed(1)} s</small>}
      </div>
    </div>
  );
});
const EFFORT_NAME: Record<string, string> = { auto: "Auto", none: "Sin razonar", low: "Bajo", high: "Alto", max: "Máximo" };

/** Cabecera de la conversación vacía, como la de Claude Code: marca quieta (una vuelta al abrir), versión, modelo y datos. */
function Banner({ settings }: { settings: AgentSettings | null }) {
  const [info, setInfo] = useState<Doctor | null>(null);
  useEffect(() => { api.doctor().then(setInfo).catch(() => undefined); }, []);
  const model = settings ? (settings.providers[settings.provider]?.model_names?.[settings.model] ?? settings.model) : null;
  return (
    <div className="term-banner">
      <RadarMark size={30} intro />
      <div>
        <div><b>radar</b> <span className="term-dim">{info ? `v${info.version}` : ""}</span></div>
        <div className="term-banner-model">{settings?.ready && model ? `${model} · ${EFFORT_NAME[settings.reasoning_effort] ?? settings.reasoning_effort}` : "agente sin configurar"}</div>
        <div className="term-dim">{info ? `${info.career} · ${info.jobs.active.toLocaleString("es-PE")} ofertas` : ""}</div>
      </div>
    </div>
  );
}

/** «✻ Analizando… (12 s · ↓1,2k tokens · esc para detener)», como el indicador de Claude Code. */
function Working({ startedAt, tokens, phase }: { startedAt: number; tokens: number; phase?: "thinking" | "writing" }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(id); }, []);
  const seconds = Math.max(0, Math.round((now - startedAt) / 1000));
  const count = tokens >= 1000 ? `${(tokens / 1000).toFixed(1)}k` : String(tokens);
  const label = phase === "thinking" ? "Razonando…" : "Analizando…";
  return <div className="term-line term-tool is-working"><span className="term-glyph"><RadarMark spinning /></span><div className="term-body">{label} <span className="term-dim">({seconds} s{tokens > 0 ? ` · ↓${count} tokens` : ""} · esc para detener)</span></div></div>;
}
const SETUP_PROMPT = "Ayúdame a configurar Radar";
const transcriptOf = (lines: { kind: string; text: string }[]) =>
  lines.map((l) => (l.kind === "user" ? `**❯ ${l.text}**` : l.kind === "tool" ? `> ${l.text}` : l.text)).join("\n\n");

/** Terminal minimal: líneas con prefijo, respuestas en Markdown, comandos con `/` y aprobación con teclado. */
export default function AgentChatPanel({ chat, onSettings, dock, onClose }: { chat: Chat; context?: AgentContext; onSettings: () => void; dock?: { pinned: boolean; toggle: () => void }; onClose?: () => void }) {
  const [input, setInput] = useState("");
  const [pastedBlocks, setPastedBlocks] = useState<PastedBlock[]>([]);
  const [images, setImages] = useState<AttachedImage[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const pasteCounter = useRef(0);
  const imageCounter = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [menuIndex, setMenuIndex] = useState(0);
  const [menuOpen, setMenuOpen] = useState(true);
  const [configMenu, setConfigMenu] = useState<"model" | "effort" | null>(null);
  const [resumeOpen, setResumeOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);  // texto tras «@» junto al cursor
  const [mentionItems, setMentionItems] = useState<(Mention & { label: string; hint: string })[]>([]);
  const [mentionIndex, setMentionIndex] = useState(0);
  const picked = useRef<Mention[]>([]);  // menciones elegidas en este mensaje
  const [panel, setPanel] = useState<{ title: string; text: string } | null>(null);  // ventana temporal (/help, /status…)
  const [notice, setNotice] = useState<string | null>(null);  // aviso breve que se apaga solo
  const noticeTimer = useRef<number | null>(null);
  const showNotice = (text: string) => {
    setNotice(text);
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), 3500);
  };
  const [expandTools, setExpandTools] = useState(false);  // Ctrl+O: mostrar el resultado completo de las herramientas
  const [queuedPrompt, setQueuedPrompt] = useState<{ text: string; pasted: PastedBlock[]; images: AttachedImage[] } | null>(null);
  const recall = useRef<{ list: string[]; at: number }>({ list: [], at: -1 });
  const bottom = useRef<HTMLDivElement>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const { lines, pending, busy, deciding, settings, needsSetup, send, decide, decideAll, stop, reset, addLocal, refreshSettings, open, remove, list, compact, usage, turn, title, rename: renameChat, planMode, setPlanMode, autoMode, setAutoMode, planReady, setPlanReady, approvePlan, contextMode, setContextMode, rewind } = chat;
  const matches = menuOpen ? matchCommands(input) : [];
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [lines, pending, busy]);
  useEffect(() => { setMenuIndex(0); setMenuOpen(true); }, [input]);
  useEffect(() => {
    const el = promptRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;  // crece hasta ~6 líneas
  }, [input]);
  useEffect(() => {
    if (mentionQuery === null) { setMentionItems([]); return; }
    let live = true;
    const timer = window.setTimeout(() => {
      api.mentions(mentionQuery).then((r) => {
        if (!live) return;
        setMentionItems([
          ...r.places.map((p) => ({ ...p, label: p.name, hint: p.kind === "district" ? "distrito" : "ciudad" })),
          ...r.jobs.map((j) => ({ ...j, label: j.name, hint: j.company ?? "oferta" })),
        ]);
        setMentionIndex(0);
      }).catch(() => setMentionItems([]));
    }, 140);
    return () => { live = false; window.clearTimeout(timer); };
  }, [mentionQuery]);
  useEffect(() => { if (!configMenu && !resumeOpen && !panel) promptRef.current?.focus(); }, [configMenu, resumeOpen, panel]);

  // Atajos globales para tarjetas de confirmación cuando el foco no está escribiendo en el prompt.
  useEffect(() => {
    if ((!pending.length && !planReady) || Boolean(deciding)) return;
    const onGlobalKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      const inOtherInput = target && target !== promptRef.current && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable);
      if (inOtherInput) return;
      if (target === promptRef.current && input !== "") return;
      const key = event.key.toLowerCase();
      if (pending.length) {
        if (["y", "1"].includes(key)) { event.preventDefault(); void decide(pending[0], true, false); return; }
        if (key === "2") { event.preventDefault(); void decide(pending[0], true, true); return; }
        if (["n", "3"].includes(key)) { event.preventDefault(); void decide(pending[0], false, false); return; }
        if (key === "a" && pending.length > 1) { event.preventDefault(); void decideAll(true); return; }
      } else if (planReady && !busy) {
        if (key === "1") { event.preventDefault(); void approvePlan(); return; }
        if (key === "2") { event.preventDefault(); setPlanReady(false); return; }
      }
    };
    window.addEventListener("keydown", onGlobalKey);
    return () => window.removeEventListener("keydown", onGlobalKey);
  }, [pending, planReady, busy, deciding, input, decide, decideAll, approvePlan, setPlanReady]);

  // Despacha mensaje en cola en cuanto el turno actual y las confirmaciones terminan.
  useEffect(() => {
    if (!queuedPrompt || busy || Boolean(deciding) || pending.length > 0) return;
    const next = queuedPrompt;
    setQueuedPrompt(null);
    const used = picked.current.filter((m) => next.text.includes(`@${(m.name.length > 40 ? `${m.name.slice(0, 39)}…` : m.name).replace(/\s+/g, "_")}`));
    picked.current = [];
    void send(next.text, used, { pastedBlocks: next.pasted, images: next.images });
  }, [queuedPrompt, busy, deciding, pending.length, send]);

  const applyConfig = async (model: string, effort: "auto" | "none" | "low" | "high" | "max") => {
    if (!settings) return;
    try { await api.saveAgentSettings({ provider: settings.provider, model, reasoning_effort: effort }); await refreshSettings(); }
    catch { onSettings(); }
  };

  const attachImageFiles = async (files: File[]) => {
    const imageFiles = files.filter((f) => f.type.startsWith("image/"));
    if (!imageFiles.length) return;
    for (const file of imageFiles) {
      if (images.length >= MAX_IMAGES_PER_TURN) {
        showNotice(`Máximo ${MAX_IMAGES_PER_TURN} imágenes por turno.`);
        break;
      }
      try {
        const compressed = await compressImageFile(file);
        imageCounter.current += 1;
        const id = imageCounter.current;
        setImages((prev) => (prev.length >= MAX_IMAGES_PER_TURN ? prev : [...prev, { id, ...compressed }]));
      } catch (err) {
        showNotice(err instanceof Error ? err.message : "No se pudo adjuntar la imagen.");
      }
    }
  };

  const onPaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = Array.from(event.clipboardData?.items ?? []);
    const imageFiles = items
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter((f): f is File => f !== null);
    if (imageFiles.length > 0) {
      event.preventDefault();
      void attachImageFiles(imageFiles);
      return;
    }
    const pastedText = event.clipboardData?.getData("text/plain") ?? "";
    if (!pastedText) return;
    const lineCount = pastedText.split(/\r?\n/).length;
    if (lineCount >= PASTE_COLLAPSE_MIN_LINES || pastedText.length >= PASTE_COLLAPSE_MIN_CHARS) {
      event.preventDefault();
      pasteCounter.current += 1;
      const id = pasteCounter.current;
      setPastedBlocks((prev) => [...prev, { id, lines: lineCount, chars: pastedText.length, text: pastedText }]);
    }
  };

  const lastAssistant = lines.map((l) => l.kind).lastIndexOf("assistant");
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
  /** Shift+Tab: manual → auto → plan → manual. Solo cambia el indicador del pie; no escribe nada en el chat. */
  const cycleMode = () => {
    if (planMode) { setPlanMode(false); setPlanReady(false); }
    else if (autoMode) setPlanMode(true);
    else setAutoMode(true);
  };

  const onInput = (value: string, caret: number) => {
    setInput(value);
    const match = /(^|\s)@([^\s@]{0,40})$/.exec(value.slice(0, caret));
    setMentionQuery(match ? match[2] : null);
  };
  const pickMention = (item: (typeof mentionItems)[number]) => {
    const el = promptRef.current;
    const caret = el?.selectionStart ?? input.length;
    const before = input.slice(0, caret).replace(/@[^\s@]{0,40}$/, "");
    const label = item.type === "job" && item.label.length > 40 ? `${item.label.slice(0, 39)}…` : item.label;
    const token = `@${label.replace(/\s+/g, "_")}`;
    setInput(`${before}${token} ${input.slice(caret)}`);
    picked.current = [...picked.current, item.type === "place" ? { type: "place", name: item.name } : { type: "job", id: item.id, name: item.name, company: item.company }];
    setMentionQuery(null);
    window.setTimeout(() => el?.focus(), 0);
  };

  const submit = async (raw: string) => {
    const text = raw.trim();
    const hasAttachments = pastedBlocks.length > 0 || images.length > 0;
    if (!text && !hasAttachments) return;
    if (busy || Boolean(deciding)) {
      if (!text.startsWith("/")) {
        setQueuedPrompt({ text, pasted: pastedBlocks, images });
        setInput("");
        setPastedBlocks([]);
        setImages([]);
        showNotice("Mensaje en cola: se enviará al terminar el turno actual.");
      }
      return;
    }
    if (text) recall.current = { list: [...recall.current.list, text].slice(-50), at: -1 };
    search.current = null;
    const currentPasted = pastedBlocks;
    const currentImages = images;
    setInput("");
    setPastedBlocks([]);
    setImages([]);
    if (text.startsWith("#") && !hasAttachments) {
      // Atajo de memoria: "# prefiero híbrido" lo recuerda en cada conversación.
      addLocal(text, "user");
      const note = text.replace(/^#+\s*/, "").trim();
      try { const { items } = await import("../../lib/mobile-api").then((m) => m.api.memory()); await import("../../lib/mobile-api").then((m) => m.api.setMemory([...items, note])); addLocal(`Anotado: _${note}_`); }
      catch (error) { addLocal(error instanceof Error ? error.message : "No se pudo guardar.", "error"); }
      return;
    }
    if (!text.startsWith("/") || hasAttachments) {
      const used = picked.current.filter((m) => text.includes(`@${(m.name.length > 40 ? `${m.name.slice(0, 39)}…` : m.name).replace(/\s+/g, "_")}`));
      picked.current = [];
      await send(text, used, { pastedBlocks: currentPasted, images: currentImages });
      return;
    }
    const [head, ...rest] = text.slice(1).split(/\s+/);
    const command = findCommand(head.toLowerCase());
    if (!command?.view) addLocal(text, "user");  // los comandos de ventana o aviso no se muestran en el chat
    if (!command) { addLocal(`Comando desconocido: \`/${head}\`. Prueba \`/ayuda\`.`, "error"); return; }
    try {
      const out = await command.run(rest.join(" "), {
        send, reset, refreshSettings, open, remove, list, compact, usage, openConfigMenu: (section = "model") => setConfigMenu(section), openResume: () => setResumeOpen(true), rename: renameChat, title, plan: { active: planMode, set: (on) => { setPlanMode(on); if (!on) setPlanReady(false); } }, dock, close: onClose,
        transcript: () => transcriptOf(lines),
        lastAnswer: () => [...lines].reverse().find((l) => l.kind === "assistant" || l.kind === "local")?.text ?? "",
      });
      if (out) {
        if (command.view === "panel") setPanel({ title: `/${command.name}`, text: out });
        else if (command.view === "notice") showNotice(out);
        else addLocal(out);
      }
    } catch (error) { addLocal(error instanceof Error ? error.message : "El comando falló.", "error"); }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (mentionQuery !== null && mentionItems.length) {
      if (event.key === "ArrowDown") { event.preventDefault(); setMentionIndex((i) => (i + 1) % mentionItems.length); return; }
      if (event.key === "ArrowUp") { event.preventDefault(); setMentionIndex((i) => (i - 1 + mentionItems.length) % mentionItems.length); return; }
      if (event.key === "Tab" || event.key === "Enter") { event.preventDefault(); pickMention(mentionItems[mentionIndex]); return; }
      if (event.key === "Escape") { event.preventDefault(); setMentionQuery(null); return; }
    }
    if (matches.length) {
      if (event.key === "ArrowDown") { event.preventDefault(); setMenuIndex((i) => (i + 1) % matches.length); return; }
      if (event.key === "ArrowUp") { event.preventDefault(); setMenuIndex((i) => (i - 1 + matches.length) % matches.length); return; }
      if (event.key === "Escape") { event.preventDefault(); setMenuOpen(false); return; }
      if (event.key === "Tab" || (event.key === "Enter" && input !== `/${matches[menuIndex].name}`)) {
        event.preventDefault(); const c = matches[menuIndex]; setInput(`/${c.name}${c.args ? " " : ""}`); return;
      }
    }
    if (event.key === "Backspace" && input === "") {
      if (images.length > 0) { event.preventDefault(); setImages((prev) => prev.slice(0, -1)); return; }
      if (pastedBlocks.length > 0) { event.preventDefault(); setPastedBlocks((prev) => prev.slice(0, -1)); return; }
    }
    if (event.key === "PageUp" || event.key === "PageDown") {  // sin barra visible, el registro se recorre con el teclado
      const log = logRef.current;
      if (log) { event.preventDefault(); log.scrollBy({ top: (event.key === "PageUp" ? -1 : 1) * log.clientHeight * 0.85 }); }
      return;
    }
    if (event.key === "Enter" && event.shiftKey) return;  // salto de línea
    if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (input.endsWith("\\")) { setInput(`${input.slice(0, -1)}\n`); return; }  // «\» + Enter también inserta salto
      void submit(input); return;
    }
    if (event.key === "Escape" && busy) { event.preventDefault(); stop(); return; }
    if (input === "" && pending.length && !deciding && ["y", "n", "1", "2", "3", "a"].includes(event.key.toLowerCase())) {
      const k = event.key.toLowerCase();
      if (k === "a" && pending.length > 1) { event.preventDefault(); void decideAll(true); return; }
      if (k !== "a") {
        event.preventDefault();
        void decide(pending[0], k !== "n" && k !== "3", k === "2"); return;
      }
    }
    if (input === "" && planReady && !pending.length && (event.key === "1" || event.key === "2")) {
      event.preventDefault();
      if (event.key === "1") void approvePlan(); else setPlanReady(false);
      return;
    }
    if (input === "" && event.key === "?") { event.preventDefault(); setPanel({ title: "atajos", text: SHORTCUTS }); return; }
    if (event.key === "Tab" && event.shiftKey) { event.preventDefault(); cycleMode(); return; }
    if (event.ctrlKey && event.key.toLowerCase() === "o") { event.preventDefault(); setExpandTools((v) => !v); return; }
    if (event.ctrlKey && event.key.toLowerCase() === "k") { event.preventDefault(); setContextMode(contextMode === "off" ? "selection" : contextMode === "selection" ? "full" : "off"); return; }
    if (event.ctrlKey && event.key.toLowerCase() === "r") { event.preventDefault(); searchHistory(); return; }
    if (event.ctrlKey && event.key.toLowerCase() === "c" && (event.currentTarget.selectionStart === event.currentTarget.selectionEnd)) {
      event.preventDefault();
      if (busy) { stop(); return; }
      if (input || pastedBlocks.length || images.length) { setInput(""); setPastedBlocks([]); setImages([]); return; }
      const now = Date.now();
      if (now - lastCtrlC.current < 1500 && onClose) { onClose(); return; }
      lastCtrlC.current = now; addLocal("Pulsa Ctrl+C otra vez para salir."); return;
    }
    if (event.key === "Escape" && !busy && !input && !pastedBlocks.length && !images.length) {
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
    <div
      className={`m-chat term${dragActive ? " is-drag-over" : ""}`}
      onDragOver={(e) => {
        if (Array.from(e.dataTransfer?.types ?? []).includes("Files")) {
          e.preventDefault();
          setDragActive(true);
        }
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragActive(false);
      }}
      onDrop={(e) => {
        setDragActive(false);
        const files = Array.from(e.dataTransfer?.files ?? []);
        if (files.some((f) => f.type.startsWith("image/"))) {
          e.preventDefault();
          void attachImageFiles(files);
        }
      }}
    >
      {settings && !settings.ready && (
        <button className="m-callout" onClick={onSettings}>
          <strong>Falta tu clave de API</strong>
          <span>Los comandos con <code>/</code> funcionan sin clave; para conversar con el agente hace falta la tuya (por ejemplo DeepSeek). Toca para configurar.</span>
        </button>
      )}
      <div className="term-log" aria-live="polite" ref={logRef}>
        {lines.length === 0 && (
          <div className="term-welcome">
            <Banner settings={settings} />
            <span className="term-dim">escribe <b>/</b> para comandos · <b>?</b> atajos{needsSetup ? " · " : ""}{needsSetup && <button onClick={() => send(SETUP_PROMPT)}>/init</button>}</span>
          </div>
        )}
        {lines.map((line, index) => <TermLine key={index} line={line} expanded={expandTools} streaming={busy && index === lastAssistant} />)}
        {pending.length > 1 && (
          <div className="term-confirm term-confirm-batch">
            <div><b>{pending.length} acciones propuestas en lote</b></div>
            <div className="m-actions">
              <button type="button" disabled={Boolean(deciding)} onClick={() => void decideAll(true)}>
                {deciding === "__all__" ? "Ejecutando lote…" : `[A] Sí a todas (${pending.length})`}
              </button>
              <button type="button" disabled={Boolean(deciding)} onClick={() => void decideAll(false)}>
                Rechazar todas
              </button>
            </div>
          </div>
        )}
        {pending.map((action) => {
          const isDecidingThis = deciding === action.id || deciding === "__all__";
          return (
            <div className={`term-confirm${isDecidingThis ? " is-deciding" : ""}`} key={action.id}>
              <div><b>Acción propuesta:</b> {action.description}</div>
              {action.preview?.length ? <ul className="term-preview">{action.preview.map((line) => <li key={line}>{line}</li>)}</ul> : <code>{action.name}({JSON.stringify(action.arguments)})</code>}
              <div className="m-actions">
                <button type="button" disabled={Boolean(deciding)} onClick={() => void decide(action, true)}>
                  {isDecidingThis ? "Ejecutando…" : "[1] Sí"}
                </button>
                <button type="button" disabled={Boolean(deciding)} onClick={() => void decide(action, true, true)}>
                  [2] Sí, y no preguntar más esta sesión
                </button>
                <button type="button" disabled={Boolean(deciding)} onClick={() => void decide(action, false)}>
                  [3] No
                </button>
              </div>
            </div>
          );
        })}
        {planReady && !busy && !pending.length && (
          <div className="term-confirm">
            <div><b>Plan listo.</b> ¿Lo ejecuto?</div>
            <div className="m-actions">
              <button type="button" onClick={() => void approvePlan()}>[1] Aprobar y ejecutar</button>
              <button type="button" onClick={() => setPlanReady(false)}>[2] Seguir planificando</button>
            </div>
          </div>
        )}
        {busy && <Working startedAt={turn?.startedAt ?? Date.now()} tokens={turn?.tokens ?? 0} phase={turn?.phase} />}
        <div ref={bottom} />
      </div>
      {mentionQuery !== null && mentionItems.length > 0 && (
        <ul className="term-menu" role="listbox" aria-label="Menciones">
          {mentionItems.map((m, i) => (
            <li key={`${m.type}-${m.label}-${i}`} role="option" aria-selected={i === mentionIndex} className={i === mentionIndex ? "on" : ""}
              onMouseDown={(e) => { e.preventDefault(); pickMention(m); }}>
              <span>@{m.label}</span><small>{m.hint}</small>
            </li>
          ))}
        </ul>
      )}
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
      {(pastedBlocks.length > 0 || images.length > 0 || queuedPrompt !== null) && (
        <div className="term-StagingBar" aria-label="Adjuntos del mensaje">
          {queuedPrompt && (
            <span className="term-stage-chip">
              <span className="term-stage-label" title={queuedPrompt.text}>
                [En cola: {queuedPrompt.text.length > 42 ? `${queuedPrompt.text.slice(0, 42)}…` : queuedPrompt.text || "adjunto"}]
              </span>
              <button
                type="button"
                className="term-stage-remove"
                aria-label="Cancelar mensaje en cola"
                onClick={() => setQueuedPrompt(null)}
              >
                ×
              </button>
            </span>
          )}
          {pastedBlocks.map((b) => (
            <span key={`stage-p-${b.id}`} className="term-stage-chip">
              <button
                type="button"
                className="term-stage-label"
                title="Clic para inspeccionar texto pegado"
                onClick={() => setPanel({ title: `Pasted text #${b.id} (${b.lines} lines)`, text: `\`\`\`\n${b.text.slice(0, 4000)}\n\`\`\`` })}
              >
                [Pasted text #{b.id} +{b.lines} lines]
              </button>
              <button
                type="button"
                className="term-stage-remove"
                aria-label={`Quitar texto pegado #${b.id}`}
                onClick={() => setPastedBlocks((prev) => prev.filter((x) => x.id !== b.id))}
              >
                ×
              </button>
            </span>
          ))}
          {images.map((img) => (
            <span key={`stage-i-${img.id}`} className="term-stage-chip">
              <button
                type="button"
                className="term-stage-label"
                title={img.name || `Image #${img.id}`}
                onClick={() => setPanel({ title: `Image #${img.id} (${img.width}×${img.height})`, text: `Dimensiones: **${img.width}×${img.height} px** · Se enviará con visión multimodal (\`deepseek-flash\`).` })}
              >
                [Image #{img.id} · {img.width}×{img.height}]
              </button>
              <button
                type="button"
                className="term-stage-remove"
                aria-label={`Quitar imagen #${img.id}`}
                onClick={() => setImages((prev) => prev.filter((x) => x.id !== img.id))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <form className="term-prompt" onSubmit={(e) => { e.preventDefault(); void submit(input); }}>
        <span className="term-glyph" aria-hidden>❯</span>
        <textarea
          ref={promptRef}
          rows={1}
          value={input}
          onChange={(e) => onInput(e.target.value, e.target.selectionStart)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          placeholder="pregunta, pega texto/captura o / para comandos"
          aria-label="Mensaje"
          maxLength={40000}
          autoComplete="off"
          spellCheck={false}
        />
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (files.length) void attachImageFiles(files);
          }}
        />
        {!busy && (
          <button
            type="button"
            className="term-attach-trigger"
            title="Adjuntar captura o imagen (también puedes pegar con Ctrl+V o arrastrar)"
            aria-label="Adjuntar imagen"
            onClick={() => fileInputRef.current?.click()}
          >
            🖼
          </button>
        )}
        {busy && <button type="button" onClick={stop}>esc</button>}
      </form>
      {panel && <InfoPanel title={panel.title} text={panel.text} onClose={() => setPanel(null)} />}
      {resumeOpen && <ResumePicker onOpen={open} onDelete={(id) => remove(id)} onClose={() => setResumeOpen(false)} />}
      {configMenu && settings && <ConfigPicker settings={settings} focus={configMenu} onApply={applyConfig} onClose={() => setConfigMenu(null)} />}
      {notice && <div className="term-notice" role="status"><Markdown text={notice} /></div>}
      <div className="term-footer">
        <span>
          <span className={`term-mode term-mode-${planMode ? "plan" : autoMode ? "auto" : "manual"}`}>{planMode ? "plan mode on" : autoMode ? "auto mode on" : "manual mode on"}</span>
          <span className="term-dim"> (shift+tab)</span>
          {settings?.read_only ? <span className="term-readonly"> · read-only (/readonly off)</span> : null}
          {contextMode === "off" ? <span className="term-dim"> · no context</span> : contextMode === "full" ? <span className="term-dim"> · full context</span> : null}
        </span>
      </div>
    </div>
  );
}
