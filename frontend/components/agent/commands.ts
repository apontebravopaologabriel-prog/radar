import { api, STATUS_LABELS, STATUS_ORDER, type ConversationInfo } from "../../lib/mobile-api";
import { BASE_PROMPT_TOKENS } from "./useAgentChat";

/** Comandos con `/` del agente. Los "local" se resuelven con la API de Radar (sin gastar tokens);
 *  los "prompt" envían una instrucción al modelo. */
export type CommandContext = {
  send: (text: string) => Promise<void>;
  reset: () => void;
  refreshSettings: () => void;
  open: (id: string) => Promise<void>;
  remove: (id?: string) => Promise<void>;
  list: () => Promise<ConversationInfo[]>;
  compact: (focus?: string) => Promise<string>;
  openConfigMenu: (section?: "model" | "effort") => void;
  openResume: () => void;
  rename: (title: string) => void;
  title: string;
  plan: { active: boolean; set: (on: boolean) => void };
  transcript: () => string;
  usage: { context: number; session: number; estimated: boolean };
  lastAnswer: () => string;
  dock?: { pinned: boolean; toggle: () => void };
  close?: () => void;
};
let lastList: ConversationInfo[] = [];
export type Command = {
  name: string;
  aliases?: string[];
  args?: string;
  hint: string;
  kind: "local" | "prompt";
  /** «panel»: ventana temporal que se cierra con Esc; «notice»: aviso breve. Sin valor, la respuesta va al chat. */
  view?: "panel" | "notice";
  run: (args: string, ctx: CommandContext) => Promise<string | null>;
};

export const SHORTCUTS = [
  "**Atajos de teclado**", "",
  "| Tecla | Acción |", "|---|---|",
  "| `Enter` / `Shift+Enter` | Enviar / nueva línea (también `\\` + Enter) |",
  "| `/` · `Tab` · `↑↓` | Comandos, autocompletar y elegir |",
  "| `↑` (vacío) | Recuperar mensajes anteriores |",
  "| `Ctrl+R` | Buscar en el historial (repite para el siguiente) |",
  "| `Esc` | Detener la respuesta |",
  "| `PgUp` / `PgDn` | Recorrer la conversación (sin barra de desplazamiento) |",
  "| `Esc Esc` | Volver a tu último mensaje para editarlo |",
  "| `Shift+Tab` | Modo: manual → auto → plan (se ve abajo; auto aprueba solo el seguimiento personal) |",
  "| `/resume` → `Ctrl+D` | Borrar la conversación resaltada (pide confirmar) |",
  "| `Ctrl+O` | Mostrar u ocultar el resultado completo de las herramientas |",
  "| `Ctrl+K` | Contexto de pantalla: apagado → selección → completo |",
  "| `Ctrl+C` | Detener; con el campo vacío, dos veces cierra |",
  "| `1` `2` `3` | Aprobar / aprobar siempre (sesión) / rechazar (`y` y `n` también) |",
  "| `@` | Citar un distrito, ciudad u oferta (`Tab` o `Enter` elige) |",
  "| `#` texto | Guardar en memoria |",
  "| `?` (vacío) | Esta ayuda |",
].join("\n");

const k = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));
const meter = (pct: number, width = 20) => {
  const filled = Math.min(width, Math.round((pct / 100) * width));
  return `${"█".repeat(filled)}${"░".repeat(width - filled)}`;
};
const cut = (value: string | null | undefined, n = 44) => (value && value.length > n ? `${value.slice(0, n - 1)}…` : value ?? "—");
const esc = (value: string | null | undefined) => (value ?? "—").replace(/\|/g, "\\|");

export const COMMANDS: Command[] = [
  { name: "help", aliases: ["ayuda", "?"], hint: "Lista de comandos", kind: "local", run: async () =>
      ["**Comandos** (escribe `/` para verlos):", "", ...COMMANDS.map((c) => `- \`/${c.name}${c.args ? ` ${c.args}` : ""}\` — ${c.hint}`),
        "", "Sin `/`, escribe con normalidad y el agente responde."].join("\n") },
  { name: "today", aliases: ["hoy"], hint: "Ofertas frescas que encajan contigo", kind: "local", run: async () => {
      const { jobs, profile_configured } = await api.today();
      if (!jobs.length) return "Nada nuevo por ahora. Prueba `/refresh`.";
      const rows = jobs.slice(0, 8).map((j) => `| ${esc(cut(j.title))} | ${esc(cut(j.company, 22))} | ${j.score === null ? "—" : `${Math.round(j.score)}%`} | ${esc(cut(j.why, 46))} |`);
      return [profile_configured ? "" : "_Sin perfil: configura `/status`._", "| Oferta | Empresa | Encaje | Por qué |", "|---|---|---|---|", ...rows].join("\n");
    } },
  { name: "map", aliases: ["mapa", "near"], args: "<lugar> [km]", hint: "Ofertas cerca de un distrito o ciudad", kind: "local", run: async (args) => {
      const parts = args.trim().split(/\s+/).filter(Boolean);
      const last = parts.at(-1);
      const km = last && /^\d+(\.\d+)?$/.test(last) ? Number(parts.pop()) : 10;
      const place = parts.join(" ") || (await api.places()).default || "Lima";
      const data = await api.nearby(place, km);
      if (!data.jobs.length) return `Nada a ${km} km de **${data.origin}**.`;
      const rows = data.jobs.slice(0, 10).map((j) => `| ${esc(cut(j.title))} | ${esc(cut(j.company, 22))} | ${esc(j.place)} | ${j.precision === "department" ? "dpto." : `${Math.round(j.km)} km`} |`);
      return [`**${data.total}** ofertas a ${km} km de **${data.origin}**`, "", "| Oferta | Empresa | Lugar | Dist. |", "|---|---|---|---|", ...rows].join("\n");
    } },
  { name: "pipeline", aliases: ["proceso", "tracking"], hint: "Tu seguimiento de postulaciones", kind: "local", run: async () => {
      const { applications } = await api.applications();
      if (!applications.length) return "Aún no sigues ninguna oferta. Guarda alguna desde `/today`.";
      const counts = STATUS_ORDER.map((s) => `${STATUS_LABELS[s]}: **${applications.filter((a) => a.status === s).length}**`).join(" · ");
      const recent = applications.slice(0, 6).map((a) => `- ${a.title} — ${a.company ?? "—"} \`${a.status}\``);
      return [counts, "", ...recent].join("\n");
    } },
  { name: "skills", hint: "Qué skill te sube más el encaje", kind: "local", run: async () => {
      const data = await api.impact();
      if (!data.profile_configured) return "Configura tu perfil primero (`/status`).";
      if (!data.skills.length) return "No hay skills faltantes que simular.";
      return ["| Skill | Ofertas | Sube (pts) | Pasan a encaje alto |", "|---|---|---|---|",
        ...data.skills.map((s) => `| ${esc(s.skill)} | ${s.jobs} | +${s.avg_gain} | ${s.crossing} |`)].join("\n");
    } },
  { name: "status", aliases: ["estado"], hint: "Qué falta para dejar Radar listo", kind: "local", run: async () => {
      const { steps } = await api.setupStatus();
      return steps.map((s) => `- ${s.done ? "✓" : "✗"} **${s.id}** — ${s.detail}`).join("\n");
    } },
  { name: "profile", aliases: ["perfil"], hint: "Tu perfil declarado", kind: "local", run: async () => {
      const { profile } = await api.profile();
      if (!profile) return "Sin perfil. Usa `/status` o pídele al agente que te ayude a configurarlo.";
      const skills = Object.entries(profile.skills).map(([k, v]) => `${k} (${v})`).join(", ") || "—";
      return [`**${profile.name}** · ${profile.education ?? "sin formación"}`, `- Áreas: ${profile.target_roles.join(", ") || "—"}`,
        `- Dónde: ${profile.locations.join(", ") || "—"}`, `- Skills: ${skills}`].join("\n");
    } },
  { name: "keys", aliases: ["atajos", "shortcuts"], hint: "Atajos de teclado", kind: "local", run: async () => SHORTCUTS },
  { name: "context", aliases: ["contexto"], hint: "Cuánto contexto ocupa esta conversación", kind: "local", run: async (_a, ctx) => {
      const s = await api.agentSettings();
      const window = s.context_window;
      const used = ctx.usage.context;
      if (!used) return "Aún no hay llamadas al modelo en esta conversación.";
      const pct = Math.min(100, Math.round((used / window) * 100));
      const base = Math.min(BASE_PROMPT_TOKENS, used);
      return [`\`${meter(pct)}\` **${pct}%**${ctx.usage.estimated ? " _(estimado)_" : ""}`, "",
        `${k(used)} de ${k(window)} tokens (ventana configurada; ajústala en Ajustes)`,
        `- Sistema y herramientas: ~${k(base)}`, `- Conversación: ~${k(Math.max(used - base, 0))}`,
        `- Sesión (todas las llamadas): ${k(ctx.usage.session)}`,
        pct >= 70 ? "\n**Se está llenando: usa `/compact`.**" : ""].join("\n");
    } },
  { name: "compact", aliases: ["compactar"], args: "[foco]", hint: "Resume la conversación para liberar contexto", kind: "local", run: async (args, ctx) => ctx.compact(args.trim()) },
  { name: "cost", aliases: ["costo", "tokens", "usage"], hint: "Modelo y tokens usados este mes", kind: "local", run: async () => {
      const s = await api.agentSettings();
      const pct = Math.round((s.tokens_used_this_month / Math.max(s.monthly_token_cap, 1)) * 100);
      return `\`${meter(pct)}\` **${pct}%** del tope mensual\n\n**${s.provider}** · \`${s.model}\`\n${s.tokens_used_this_month.toLocaleString("es-PE")} de ${s.monthly_token_cap.toLocaleString("es-PE")} tokens${s.read_only ? " · solo lectura" : ""}`;
    } },
  { name: "model", aliases: ["models", "modelo", "modelos"], args: "[nombre]", hint: "Ver o cambiar el modelo", kind: "local", run: async (args, ctx) => {
      const s = await api.agentSettings();
      const wanted = args.trim();
      if (!wanted) { ctx.openConfigMenu("model"); return null; }
      await api.saveAgentSettings({ provider: s.provider, model: wanted });
      ctx.refreshSettings();
      return `Modelo cambiado a \`${wanted}\`.`;
    } },
  { name: "effort", aliases: ["esfuerzo", "thinking"], args: "[auto|none|low|high|max]", hint: "Cambiar el esfuerzo de razonamiento", kind: "local", run: async (args, ctx) => {
      const s = await api.agentSettings();
      const wanted = args.trim().toLowerCase();
      if (!wanted) { ctx.openConfigMenu("effort"); return null; }
      if (!(s.providers[s.provider]?.reasoning_efforts ?? []).includes(wanted) && wanted !== "auto") return "Effort inválido. Usa `auto`, `none`, `low`, `high` o `max`.";
      await api.saveAgentSettings({ provider: s.provider, reasoning_effort: wanted as "auto" | "none" | "low" | "high" | "max" });
      ctx.refreshSettings();
      return `Effort cambiado a \`${wanted}\`.`;
    } },
  { name: "pin", aliases: ["fijar"], hint: "Fija el agente a la derecha o lo vuelve ventana", kind: "local", run: async (_a, ctx) => {
      if (!ctx.dock) return "Fijar solo está disponible en la versión de escritorio.";
      ctx.dock.toggle();
      return null;
    } },
  { name: "copy", aliases: ["copiar"], hint: "Copia la última respuesta", kind: "local", run: async (_a, ctx) => {
      const text = ctx.lastAnswer();
      if (!text) return "No hay respuesta que copiar.";
      await navigator.clipboard.writeText(text);
      return "Copiado al portapapeles.";
    } },
  { name: "exit", aliases: ["salir", "cerrar", "quit"], hint: "Cierra la ventana del agente", kind: "local", run: async (_a, ctx) => { ctx.close?.(); return null; } },
  { name: "refresh", aliases: ["actualizar"], hint: "Traer ofertas nuevas de tu carrera", kind: "local", run: async () => {
      const state = await api.startRefresh([]);
      return `Actualizando el mercado: ${state.total} búsquedas. Puedes seguir usando Radar; revisa \`/hoy\` en unos minutos.`;
    } },
  { name: "readonly", aliases: ["solo-lectura"], args: "[on|off]", hint: "Impide que el agente guarde cambios", kind: "local", run: async (args, ctx) => {
      const current = await api.agentSettings();
      const next = args.trim() ? args.trim() === "on" : !current.read_only;
      await api.saveAgentSettings({ provider: current.provider, read_only: next });
      ctx.refreshSettings();
      return next ? "Solo lectura **activado**: el agente ya no puede guardar nada." : "Solo lectura **desactivado**: las acciones piden tu aprobación.";
    } },
  { name: "disable", aliases: ["apagar", "off"], hint: "Desactiva el agente", kind: "local", run: async () => {
      const current = await api.agentSettings();
      await api.saveAgentSettings({ provider: current.provider, enabled: false });
      return "Agente **apagado**. Recarga la página para ocultar la ventana; reactívalo en Ajustes.";
    } },
  { name: "resume", aliases: ["historial", "history"], hint: "Elige una conversación anterior", kind: "local", run: async (_a, ctx) => { ctx.openResume(); return null; } },
  { name: "rename", aliases: ["renombrar"], args: "<título>", hint: "Cambia el título de esta conversación", kind: "local", run: async (args, ctx) => {
      if (!ctx.title) return "Aún no hay conversación que renombrar: escribe primero un mensaje.";
      if (!args.trim()) return `Título actual: **${ctx.title}**. Usa \`/rename <título>\` o haz clic en el título de la barra superior.`;
      ctx.rename(args);
      return `Conversación renombrada.`;
    } },
  { name: "open", aliases: ["abrir"], args: "<n>", hint: "Abre una conversación del historial", kind: "local", run: async (args, ctx) => {
      if (!lastList.length) lastList = (await ctx.list()).slice(0, 10);
      const target = lastList[Number(args.trim()) - 1];
      if (!target) return "Usa `/resume` para elegir una conversación, o `/open <n>` con un número de 1 a " + lastList.length + ".";
      await ctx.open(target.id);
      return null;
    } },
  { name: "delete", aliases: ["borrar"], args: "[todo]", hint: "Borra esta conversación (o todo el historial, con confirmación)", kind: "local", run: async (args, ctx) => {
      if (args.trim() === "todo") {
        const total = (await ctx.list()).length;
        return `Esto borra **${total}** conversaciones y no se puede deshacer. Si estás seguro, escribe \`/delete todo confirmar\`.`;
      }
      if (args.trim() === "todo confirmar") { await api.deleteAllConversations(); ctx.reset(); return null; }
      await ctx.remove();
      return null;
    } },
  { name: "memory", aliases: ["memoria"], args: "[add <texto> | rm <n> | clear]", hint: "Preferencias que el agente recuerda (también: # texto)", kind: "local", run: async (args) => {
      const [verb, ...rest] = args.trim().split(/\s+/);
      const items = (await api.memory()).items;
      if (verb === "add" || verb === "+") {
        const text = rest.join(" ").trim();
        if (!text) return "Escribe qué recordar: `/memory add busco solo híbrido`.";
        await api.setMemory([...items, text]);
        return `Anotado: _${text}_`;
      }
      if (verb === "rm" || verb === "del") {
        const n = Number(rest[0]);
        if (!items[n - 1]) return "Ese número no existe; usa `/memory` para verlas.";
        await api.setMemory(items.filter((_, i) => i !== n - 1));
        return `Olvidado: _${items[n - 1]}_`;
      }
      if (verb === "clear") { await api.setMemory([]); return "Memoria vaciada."; }
      if (!items.length) return "Sin preferencias guardadas. Añade una con `/memory add …` o escribe `# …`.";
      return ["El agente tiene en cuenta esto en cada conversación:", "", ...items.map((m, i) => `${i + 1}. ${m}`)].join("\n");
    } },
  { name: "export", hint: "Descarga la conversación en Markdown", kind: "local", run: async (_a, ctx) => {
      const text = ctx.transcript();
      if (!text) return "No hay nada que exportar.";
      const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
      const link = Object.assign(document.createElement("a"), { href: url, download: `radar-chat-${new Date().toISOString().slice(0, 10)}.md` });
      link.click();
      URL.revokeObjectURL(url);
      return "Conversación exportada.";
    } },
  { name: "doctor", hint: "Diagnóstico de la instalación", kind: "local", run: async () => {
      const d = await api.doctor();
      const ok = (v: boolean) => (v ? "✓" : "✗");
      return [`**Radar ${d.version}** · ${d.career}`, "",
        `- ${ok(d.jobs.active > 0)} Ofertas activas: ${d.jobs.active.toLocaleString("es-PE")} (${d.jobs.last_14_days.toLocaleString("es-PE")} en 14 días; última: ${d.jobs.newest_published?.slice(0, 10) ?? "—"})`,
        `- ${ok(d.agent.enabled)} Agente: ${d.agent.provider} · \`${d.agent.model}\` · clave ${d.agent.key ? "sí" : "no"}${d.agent.read_only ? " · solo lectura" : ""}`,
        `- Base de datos: ${d.database.size_mb} MB · ${d.agent.conversations} conversaciones · ${d.tools} herramientas`,
        `- ${d.refresh.running ? `Actualizando ${d.refresh.done}/${d.refresh.total}` : "Sin actualización en curso"}`].join("\n");
    } },
  { name: "tools", aliases: ["mcp", "herramientas"], hint: "Herramientas que el agente puede usar", kind: "local", run: async () => {
      const { tools, read_only_mode } = await api.agentTools();
      const reads = tools.filter((t) => !t.write); const writes = tools.filter((t) => t.write);
      return [`**Lectura (${reads.length})**: ${reads.map((t) => `\`${t.name}\``).join(", ")}`, "",
        `**Escritura con confirmación (${writes.length})**${read_only_mode ? " — _desactivadas: solo lectura_" : ""}: ${writes.map((t) => `\`${t.name}\``).join(", ")}`].join("\n");
    } },
  { name: "config", aliases: ["settings", "ajustes"], hint: "Abre los ajustes", kind: "local", run: async () => { window.location.href = "/ajustes"; return null; } },
  { name: "init", aliases: ["setup", "configurar"], hint: "El agente te guía para configurar Radar", kind: "prompt", run: async (_a, ctx) => { await ctx.send("Ayúdame a configurar Radar"); return null; } },
  { name: "clear", aliases: ["new", "nueva", "nuevo"], hint: "Empieza una conversación nueva", kind: "local", run: async (_a, ctx) => { ctx.reset(); return null; } },
  { name: "explain", aliases: ["explicar"], args: "<oferta o tema>", hint: "El agente lo explica con datos", kind: "prompt", run: async (args, ctx) => {
      await ctx.send(args.trim() ? `Explícame con datos de Radar: ${args.trim()}` : "Explícame el estado actual de mi búsqueda con datos de Radar.");
      return null;
    } },
  { name: "plan", aliases: ["planear"], args: "[texto | off]", hint: "Modo plan: el agente investiga y propone sin ejecutar", kind: "local", run: async (args, ctx) => {
      const text = args.trim();
      if (text === "off" || text === "salir") { ctx.plan.set(false); return null; }  // el modo se ve en el pie, sin ruido en el chat
      ctx.plan.set(true);
      if (text) await ctx.send(text);  // «/plan reclasifica la BD» activa el modo y lanza la petición
      return null;
    } },
  { name: "learn", aliases: ["aprender", "learning"], hint: "Plan de aprendizaje según el mercado", kind: "prompt", run: async (_a, ctx) => {
      await ctx.send("Arma mi plan de aprendizaje: usa plan_learning y get_skill_demand, ordena las skills y sé concreto.");
      return null;
    } },
  { name: "summary", aliases: ["resumen"], hint: "Resumen del mercado de hoy", kind: "prompt", run: async (_a, ctx) => {
      await ctx.send("Resume el mercado de hoy con cifras: get_market_breakdown por área y lugar, y las skills más pedidas.");
      return null;
    } },
];

// Comandos informativos: no ensucian el chat ni se guardan en la conversación.
const VIEWS: Record<string, "panel" | "notice"> = {
  help: "panel", keys: "panel", status: "panel", doctor: "panel", tools: "panel", context: "panel", cost: "panel", profile: "panel",
  copy: "notice", export: "notice", pin: "notice", readonly: "notice", refresh: "notice", model: "notice", effort: "notice",
};
for (const command of COMMANDS) command.view = VIEWS[command.name];

export const findCommand = (name: string): Command | undefined =>
  COMMANDS.find((c) => c.name === name || c.aliases?.includes(name));

export function matchCommands(input: string): Command[] {
  if (!input.startsWith("/") || input.includes(" ")) return [];
  const query = input.slice(1).toLowerCase();
  return COMMANDS.filter((c) => c.name.startsWith(query) || c.aliases?.some((a) => a.startsWith(query)));
}
