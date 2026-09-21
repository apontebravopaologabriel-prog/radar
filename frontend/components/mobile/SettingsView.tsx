"use client";

import { useEffect, useState } from "react";
import { api, type AgentSettings, type Career } from "../../lib/mobile-api";
import CustomCareerForm from "./CustomCareerForm";
import ProfileTab from "./ProfileTab";
import RefreshPanel from "./RefreshPanel";
import "./settings.css";

const WEIGHT_LABELS: Record<string, string> = {
  area: "Área", skills: "Skills", seniority: "Nivel", education: "Formación", location: "Ubicación", preference: "Modalidad",
};

type SettingsTab = "perfil" | "busqueda" | "agente" | "apariencia";
const TABS: [SettingsTab, string][] = [["perfil", "Perfil"], ["busqueda", "Búsqueda"], ["agente", "Agente"], ["apariencia", "Apariencia"]];

export default function SettingsView({ authRequired, onLogout, onError, onAgentChange }: { authRequired: boolean; onLogout: () => void; onError: (e: unknown) => void; onAgentChange?: (enabled: boolean) => void }) {
  const [career, setCareer] = useState<Career | null>(null);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [agent, setAgent] = useState<AgentSettings | null>(null);
  const [provider, setProvider] = useState("deepseek");
  const [model, setModel] = useState("");
  const [reasoningEffort, setReasoningEffort] = useState<AgentSettings["reasoning_effort"]>("auto");
  const [key, setKey] = useState("");
  const [cap, setCap] = useState(500000);
  const [ctxWindow, setCtxWindow] = useState(64000);
  const [enabled, setEnabled] = useState(false);
  const [readOnly, setReadOnly] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [note, setNote] = useState("");
  const [tab, setTab] = useState<SettingsTab>("perfil");
  const [lite, setLite] = useState(false);
  useEffect(() => { try { setLite(localStorage.getItem("radar.perf") === "lite"); } catch { /* sin almacenamiento */ } }, []);
  const toggleLite = (on: boolean) => {
    setLite(on);
    if (on) document.documentElement.dataset.perf = "lite"; else delete document.documentElement.dataset.perf;
    try { if (on) localStorage.setItem("radar.perf", "lite"); else localStorage.removeItem("radar.perf"); } catch { /* sin almacenamiento */ }
  };

  useEffect(() => {
    Promise.all([api.career(), api.agentSettings()]).then(([c, a]) => {
      setCareer(c); setWeights(c.weights); setAgent(a); setProvider(a.provider); setModel(a.model); setReasoningEffort(a.reasoning_effort); setCap(a.monthly_token_cap); setCtxWindow(a.context_window); setEnabled(a.enabled); setReadOnly(a.read_only);
    }).catch(onError);
  }, [onError]);

  const flash = (text: string) => { setNote(text); setTimeout(() => setNote(""), 2500); };
  const saveAgent = async () => {
    try {
      const next = await api.saveAgentSettings({ provider, model: model || undefined, reasoning_effort: reasoningEffort, api_key: key || undefined, monthly_token_cap: cap, context_window: ctxWindow, enabled, read_only: readOnly });
      setAgent(next); setKey(""); flash("Guardado"); onAgentChange?.(next.enabled);
    } catch (error) { onError(error); }
  };
  const pickProvider = (value: string) => {
    setProvider(value);
    setModel(agent?.providers[value]?.model ?? "");
    setReasoningEffort("auto");
  };

  if (!career || !agent) return <p className="m-empty">Cargando…</p>;
  return (
    <div className="m-stack settings-stack">
      <header className="m-head"><span className="m-eyebrow">[AJUSTES]</span><h1>Ajustes</h1>{note && <p role="status">{note}</p>}</header>
      <nav className="set-tabs" role="tablist" aria-label="Secciones de ajustes">
        {TABS.map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={tab === value} className={tab === value ? "active" : ""} onClick={() => setTab(value)}>{label}</button>)}
      </nav>
      {tab === "perfil" && <ProfileTab career={career} onError={onError} />}

      {tab === "busqueda" && (<>
      <section className="set-section">
        <h2>Carrera</h2>
        <p className="m-sub">Define las áreas, competencias y pesos con que se clasifican las ofertas nuevas.</p>
        <select value={career.active} onChange={async (e) => { try { const c = await api.setCareer(e.target.value); setCareer(c); setWeights(c.weights); flash("Carrera cambiada"); } catch (error) { onError(error); } }} aria-label="Carrera">
          {career.tracks.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <button className="m-link" onClick={() => setShowCustom(!showCustom)}>{showCustom ? "Cancelar" : "Mi carrera no está en la lista"}</button>
        {showCustom && <CustomCareerForm onError={onError} onCreated={(c) => { setCareer(c); setWeights(c.weights); setShowCustom(false); flash("Carrera creada"); }} />}
      </section>

      <section className="set-section">
        <h2>Mercado</h2>
        <p className="m-sub">Trae ofertas nuevas de tu carrera en tus ubicaciones y recalcula tu puntaje. Corre en tu equipo.</p>
        <RefreshPanel places={[]} onError={onError} />
      </section>

      <details className="set-section set-advanced">
        <summary>Qué pesa más en el encaje (avanzado)</summary>
        {Object.keys(WEIGHT_LABELS).map((k) => (
          <label className="m-slider" key={k}>
            <span>{WEIGHT_LABELS[k]} <b>{Math.round((weights[k] ?? 0) * 100)}%</b></span>
            <input type="range" min={0} max={100} value={Math.round((weights[k] ?? 0) * 100)} onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) / 100 })} />
          </label>
        ))}
        <button className="m-primary" onClick={async () => { try { const c = await api.setWeights(weights); setCareer(c); setWeights(c.weights); flash("Pesos aplicados"); } catch (error) { onError(error); } }}>Aplicar y recalcular</button>
      </details>
      </>)}

      {tab === "apariencia" && (<>
      <section className="set-section">
        <h2>Rendimiento <b>{lite ? "(modo ligero)" : "(efectos retro)"}</b></h2>
        <p className="m-sub">El modo ligero quita las líneas de escaneo, la rejilla y el barrido del mapa, y los desenfoques de los paneles. Es lo más rápido en equipos modestos. Se guarda solo en este navegador.</p>
        <label className="m-check"><input type="checkbox" checked={lite} onChange={(e) => toggleLite(e.target.checked)} />Modo ligero (sin efectos retro)</label>
      </section>

      </>)}

      {tab === "agente" && (
      <section className="set-section">
        <h2>Agente de IA <b>{enabled ? "(activado)" : "(apagado)"}</b></h2>
        <p className="m-sub">Es opcional: Radar funciona completo sin él. Usa tu propia clave: pagas al proveedor por lo que uses. La clave se guarda en tu equipo con permisos privados y nunca vuelve al navegador.</p>
        <label className="m-check"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />Activar el agente</label>
        <label className="m-check"><input type="checkbox" checked={readOnly} onChange={(e) => setReadOnly(e.target.checked)} />Solo lectura (no puede guardar nada)</label>
        <div className="settings-agent-fields">
          <label>Proveedor
            <select value={provider} onChange={(e) => pickProvider(e.target.value)}>
              {Object.keys(agent.providers).map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label>Modelo
            {(agent.providers[provider]?.models?.length ?? 0) > 0 ? (
              <select value={model} onChange={(e) => setModel(e.target.value)}>
                {agent.providers[provider].models?.map((name) => <option key={name} value={name}>{agent.providers[provider].model_names?.[name] ?? name}</option>)}
                {!agent.providers[provider].models?.includes(model) && model && <option value={model}>{model} (actual)</option>}
              </select>
            ) : <input value={model} onChange={(e) => setModel(e.target.value)} />}
          </label>
          {(agent.providers[provider]?.reasoning_efforts?.length ?? 0) > 0 && <label>Esfuerzo de razonamiento
            <select value={reasoningEffort} onChange={(e) => setReasoningEffort(e.target.value as AgentSettings["reasoning_effort"])}>
              <option value="auto">Auto (predeterminado)</option>
              <option value="none">None · más rápido</option>
              <option value="low">Low</option>
              <option value="high">High</option>
              <option value="max">Max · más lento</option>
            </select>
          </label>}
          <label>Clave de API {agent.has_key && provider === agent.provider && <b>(guardada)</b>}
            <input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={agent.has_key ? "Dejar vacío para conservar" : "sk-…"} />
          </label>
          <details className="set-advanced set-span">
            <summary>Límites (avanzado)</summary>
          <label>Tope mensual de tokens
            <input type="number" min={1000} step={50000} value={cap} onChange={(e) => setCap(Number(e.target.value))} />
          </label>
          <label>Ventana de contexto del modelo (tokens; solo para el medidor de /contexto)
            <input type="number" min={2000} step={1000} value={ctxWindow} onChange={(e) => setCtxWindow(Number(e.target.value))} />
          </label>
          </details>
        </div>
        <p className="m-sub">Usado este mes: {agent.tokens_used_this_month.toLocaleString("es-PE")} de {agent.monthly_token_cap.toLocaleString("es-PE")}.</p>
        <button className="m-primary" onClick={saveAgent}>Guardar agente</button>
      </section>
      )}

      <footer className="set-footer">
        <a className="m-link" href="/radar">Abrir mapa, análisis y CVs</a>
        {authRequired && <button className="m-link" onClick={onLogout}>Cerrar sesión</button>}
      </footer>
    </div>
  );
}
