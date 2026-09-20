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
  compact: () => Promise<string>;
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
  run: (args: string, ctx: CommandContext) => Promise<string | null>;
};

const k = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));
const meter = (pct: number, width = 20) => {
  const filled = Math.min(width, Math.round((pct / 100) * width));
  return `${"█".repeat(filled)}${"░".repeat(width - filled)}`;
};
const cut = (value: string | null | undefined, n = 44) => (value && value.length > n ? `${value.slice(0, n - 1)}…` : value ?? "—");
const esc = (value: string | null | undefined) => (value ?? "—").replace(/\|/g, "\\|");

export const COMMANDS: Command[] = [
  { name: "ayuda", hint: "Lista de comandos", kind: "local", run: async () =>
      ["**Comandos** (escribe `/` para verlos):", "", ...COMMANDS.map((c) => `- \`/${c.name}${c.args ? ` ${c.args}` : ""}\` — ${c.hint}`),
        "", "Sin `/`, escribe con normalidad y el agente responde."].join("\n") },
  { name: "hoy", hint: "Ofertas frescas que encajan contigo", kind: "local", run: async () => {
      const { jobs, profile_configured } = await api.today();
      if (!jobs.length) return "Nada nuevo por ahora. Prueba `/actualizar`.";
      const rows = jobs.slice(0, 8).map((j) => `| ${esc(cut(j.title))} | ${esc(cut(j.company, 22))} | ${j.score === null ? "—" : `${Math.round(j.score)}%`} | ${esc(cut(j.why, 46))} |`);
      return [profile_configured ? "" : "_Sin perfil: configura `/estado`._", "| Oferta | Empresa | Encaje | Por qué |", "|---|---|---|---|", ...rows].join("\n");
    } },
  { name: "mapa", args: "<lugar> [km]", hint: "Ofertas cerca de un distrito o ciudad", kind: "local", run: async (args) => {
      const parts = args.trim().split(/\s+/).filter(Boolean);
      const last = parts.at(-1);
      const km = last && /^\d+(\.\d+)?$/.test(last) ? Number(parts.pop()) : 10;
      const place = parts.join(" ") || (await api.places()).default || "Lima";
      const data = await api.nearby(place, km);
      if (!data.jobs.length) return `Nada a ${km} km de **${data.origin}**.`;
      const rows = data.jobs.slice(0, 10).map((j) => `| ${esc(cut(j.title))} | ${esc(cut(j.company, 22))} | ${esc(j.place)} | ${j.precision === "department" ? "dpto." : `${Math.round(j.km)} km`} |`);
      return [`**${data.total}** ofertas a ${km} km de **${data.origin}**`, "", "| Oferta | Empresa | Lugar | Dist. |", "|---|---|---|---|", ...rows].join("\n");
    } },
  { name: "proceso", hint: "Tu seguimiento de postulaciones", kind: "local", run: async () => {
      const { applications } = await api.applications();
      if (!applications.length) return "Aún no sigues ninguna oferta. Guarda alguna desde `/hoy`.";
      const counts = STATUS_ORDER.map((s) => `${STATUS_LABELS[s]}: **${applications.filter((a) => a.status === s).length}**`).join(" · ");
      const recent = applications.slice(0, 6).map((a) => `- ${a.title} — ${a.company ?? "—"} \`${a.status}\``);
      return [counts, "", ...recent].join("\n");
    } },
  { name: "skills", hint: "Qué skill te sube más el encaje", kind: "local", run: async () => {
      const data = await api.impact();
      if (!data.profile_configured) return "Configura tu perfil primero (`/estado`).";
      if (!data.skills.length) return "No hay skills faltantes que simular.";
      return ["| Skill | Ofertas | Sube (pts) | Pasan a encaje alto |", "|---|---|---|---|",
        ...data.skills.map((s) => `| ${esc(s.skill)} | ${s.jobs} | +${s.avg_gain} | ${s.crossing} |`)].join("\n");
    } },
  { name: "estado", hint: "Qué falta para dejar Radar listo", kind: "local", run: async () => {
      const { steps } = await api.setupStatus();
      return steps.map((s) => `- ${s.done ? "✓" : "✗"} **${s.id}** — ${s.detail}`).join("\n");
    } },
  { name: "perfil", hint: "Tu perfil declarado", kind: "local", run: async () => {
      const { profile } = await api.profile();
      if (!profile) return "Sin perfil. Usa `/estado` o pídele al agente que te ayude a configurarlo.";
      const skills = Object.entries(profile.skills).map(([k, v]) => `${k} (${v})`).join(", ") || "—";
      return [`**${profile.name}** · ${profile.education ?? "sin formación"}`, `- Áreas: ${profile.target_roles.join(", ") || "—"}`,
        `- Dónde: ${profile.locations.join(", ") || "—"}`, `- Skills: ${skills}`].join("\n");
    } },
  { name: "contexto", aliases: ["context"], hint: "Cuánto contexto ocupa esta conversación", kind: "local", run: async (_a, ctx) => {
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
        pct >= 70 ? "\n**Se está llenando: usa `/compactar`.**" : ""].join("\n");
    } },
  { name: "compactar", aliases: ["compact"], hint: "Resume la conversación para liberar contexto", kind: "local", run: async (_a, ctx) => ctx.compact() },
  { name: "costo", aliases: ["tokens", "cost"], hint: "Modelo y tokens usados este mes", kind: "local", run: async () => {
      const s = await api.agentSettings();
      const pct = Math.round((s.tokens_used_this_month / Math.max(s.monthly_token_cap, 1)) * 100);
      return `\`${meter(pct)}\` **${pct}%** del tope mensual\n\n**${s.provider}** · \`${s.model}\`\n${s.tokens_used_this_month.toLocaleString("es-PE")} de ${s.monthly_token_cap.toLocaleString("es-PE")} tokens${s.read_only ? " · solo lectura" : ""}`;
    } },
  { name: "modelo", aliases: ["model"], args: "[nombre]", hint: "Ver o cambiar el modelo", kind: "local", run: async (args, ctx) => {
      const s = await api.agentSettings();
      const wanted = args.trim();
      if (!wanted) return `**${s.provider}** · \`${s.model}\`\n\nCambia con \`/modelo <nombre>\` (ej. el nombre exacto de tu proveedor).`;
      await api.saveAgentSettings({ provider: s.provider, model: wanted });
      ctx.refreshSettings();
      return `Modelo cambiado a \`${wanted}\`.`;
    } },
  { name: "fijar", aliases: ["pin"], hint: "Fija el agente a la derecha o lo vuelve ventana", kind: "local", run: async (_a, ctx) => {
      if (!ctx.dock) return "Fijar solo está disponible en la versión de escritorio.";
      ctx.dock.toggle();
      return null;
    } },
  { name: "copiar", aliases: ["copy"], hint: "Copia la última respuesta", kind: "local", run: async (_a, ctx) => {
      const text = ctx.lastAnswer();
      if (!text) return "No hay respuesta que copiar.";
      await navigator.clipboard.writeText(text);
      return "Copiado al portapapeles.";
    } },
  { name: "salir", aliases: ["exit", "cerrar"], hint: "Cierra la ventana del agente", kind: "local", run: async (_a, ctx) => { ctx.close?.(); return null; } },
  { name: "actualizar", hint: "Traer ofertas nuevas de tu carrera", kind: "local", run: async () => {
      const state = await api.startRefresh([]);
      return `Actualizando el mercado: ${state.total} búsquedas. Puedes seguir usando Radar; revisa \`/hoy\` en unos minutos.`;
    } },
  { name: "solo-lectura", args: "[on|off]", hint: "Impide que el agente guarde cambios", kind: "local", run: async (args, ctx) => {
      const current = await api.agentSettings();
      const next = args.trim() ? args.trim() === "on" : !current.read_only;
      await api.saveAgentSettings({ provider: current.provider, read_only: next });
      ctx.refreshSettings();
      return next ? "Solo lectura **activado**: el agente ya no puede guardar nada." : "Solo lectura **desactivado**: las acciones piden tu aprobación.";
    } },
  { name: "apagar", hint: "Desactiva el agente", kind: "local", run: async () => {
      const current = await api.agentSettings();
      await api.saveAgentSettings({ provider: current.provider, enabled: false });
      return "Agente **apagado**. Recarga la página para ocultar la ventana; reactívalo en Ajustes.";
    } },
  { name: "historial", hint: "Conversaciones guardadas", kind: "local", run: async (_a, ctx) => {
      lastList = (await ctx.list()).slice(0, 10);
      if (!lastList.length) return "Aún no hay conversaciones guardadas.";
      return ["Abre una con `/abrir <n>`:", "", ...lastList.map((c, i) => `${i + 1}. ${c.title} _(${c.updated_at.slice(0, 10)})_`)].join("\n");
    } },
  { name: "abrir", args: "<n>", hint: "Abre una conversación del historial", kind: "local", run: async (args, ctx) => {
      const target = lastList[Number(args.trim()) - 1];
      if (!target) return "Primero usa `/historial` y elige un número.";
      await ctx.open(target.id);
      return null;
    } },
  { name: "borrar", args: "[todo]", hint: "Borra esta conversación (o todo el historial)", kind: "local", run: async (args, ctx) => {
      if (args.trim() === "todo") { await api.deleteAllConversations(); ctx.reset(); return null; }
      await ctx.remove();
      return null;
    } },
  { name: "nueva", aliases: ["new", "clear", "nuevo"], hint: "Empieza una conversación nueva", kind: "local", run: async (_a, ctx) => { ctx.reset(); return null; } },
  { name: "explicar", args: "<oferta o tema>", hint: "El agente lo explica con datos", kind: "prompt", run: async (args, ctx) => {
      await ctx.send(args.trim() ? `Explícame con datos de Radar: ${args.trim()}` : "Explícame el estado actual de mi búsqueda con datos de Radar.");
      return null;
    } },
  { name: "plan", hint: "Plan de aprendizaje según el mercado", kind: "prompt", run: async (_a, ctx) => {
      await ctx.send("Arma mi plan de aprendizaje: usa plan_learning y get_skill_demand, ordena las skills y sé concreto.");
      return null;
    } },
  { name: "resumen", hint: "Resumen del mercado de hoy", kind: "prompt", run: async (_a, ctx) => {
      await ctx.send("Resume el mercado de hoy con cifras: get_market_breakdown por área y lugar, y las skills más pedidas.");
      return null;
    } },
];

export const findCommand = (name: string): Command | undefined =>
  COMMANDS.find((c) => c.name === name || c.aliases?.includes(name));

export function matchCommands(input: string): Command[] {
  if (!input.startsWith("/") || input.includes(" ")) return [];
  const query = input.slice(1).toLowerCase();
  return COMMANDS.filter((c) => c.name.startsWith(query) || c.aliases?.some((a) => a.startsWith(query)));
}
