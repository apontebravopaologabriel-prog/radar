import { api, STATUS_LABELS, STATUS_ORDER } from "../../lib/mobile-api";

/** Comandos con `/` del agente. Los "local" se resuelven con la API de Radar (sin gastar tokens);
 *  los "prompt" envían una instrucción al modelo. */
export type CommandContext = {
  send: (text: string) => Promise<void>;
  reset: () => void;
  refreshSettings: () => void;
};
export type Command = {
  name: string;
  args?: string;
  hint: string;
  kind: "local" | "prompt";
  run: (args: string, ctx: CommandContext) => Promise<string | null>;
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
  { name: "costo", hint: "Modelo y tokens usados este mes", kind: "local", run: async () => {
      const s = await api.agentSettings();
      const pct = Math.round((s.tokens_used_this_month / Math.max(s.monthly_token_cap, 1)) * 100);
      return `**${s.provider}** · \`${s.model}\`\n\n${s.tokens_used_this_month.toLocaleString("es-PE")} de ${s.monthly_token_cap.toLocaleString("es-PE")} tokens (${pct}%)${s.read_only ? " · solo lectura" : ""}`;
    } },
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
  { name: "nueva", hint: "Empieza una conversación nueva", kind: "local", run: async (_a, ctx) => { ctx.reset(); return null; } },
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

export function matchCommands(input: string): Command[] {
  if (!input.startsWith("/") || input.includes(" ")) return [];
  const query = input.slice(1).toLowerCase();
  return COMMANDS.filter((c) => c.name.startsWith(query));
}
