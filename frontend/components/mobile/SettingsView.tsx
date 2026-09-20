"use client";

import { useEffect, useState } from "react";
import { api, type AgentSettings, type Career } from "../../lib/mobile-api";

const WEIGHT_LABELS: Record<string, string> = {
  area: "Área", skills: "Skills", seniority: "Nivel", education: "Formación", location: "Ubicación", preference: "Modalidad",
};

export default function SettingsView({ authRequired, onLogout, onError }: { authRequired: boolean; onLogout: () => void; onError: (e: unknown) => void }) {
  const [career, setCareer] = useState<Career | null>(null);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [agent, setAgent] = useState<AgentSettings | null>(null);
  const [provider, setProvider] = useState("deepseek");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [cap, setCap] = useState(500000);
  const [note, setNote] = useState("");

  useEffect(() => {
    Promise.all([api.career(), api.agentSettings()]).then(([c, a]) => {
      setCareer(c); setWeights(c.weights); setAgent(a); setProvider(a.provider); setModel(a.model); setCap(a.monthly_token_cap);
    }).catch(onError);
  }, [onError]);

  const flash = (text: string) => { setNote(text); setTimeout(() => setNote(""), 2500); };
  const saveAgent = async () => {
    try {
      const next = await api.saveAgentSettings({ provider, model: model || undefined, api_key: key || undefined, monthly_token_cap: cap });
      setAgent(next); setKey(""); flash("Guardado");
    } catch (error) { onError(error); }
  };
  const pickProvider = (value: string) => {
    setProvider(value);
    setModel(agent?.providers[value]?.model ?? "");
  };

  if (!career || !agent) return <p className="m-empty">Cargando…</p>;
  return (
    <div className="m-stack">
      <header className="m-head"><h1>Ajustes</h1>{note && <p role="status">{note}</p>}</header>

      <section className="m-card">
        <h2>Carrera</h2>
        <p className="m-sub">Define las áreas, competencias y pesos con que se clasifican las ofertas nuevas.</p>
        <select value={career.active} onChange={async (e) => { try { const c = await api.setCareer(e.target.value); setCareer(c); setWeights(c.weights); flash("Carrera cambiada"); } catch (error) { onError(error); } }} aria-label="Carrera">
          {career.tracks.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </section>

      <section className="m-card">
        <h2>Qué pesa más en el encaje</h2>
        {Object.keys(WEIGHT_LABELS).map((k) => (
          <label className="m-slider" key={k}>
            <span>{WEIGHT_LABELS[k]} <b>{Math.round((weights[k] ?? 0) * 100)}%</b></span>
            <input type="range" min={0} max={100} value={Math.round((weights[k] ?? 0) * 100)} onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) / 100 })} />
          </label>
        ))}
        <button className="m-primary" onClick={async () => { try { const c = await api.setWeights(weights); setCareer(c); setWeights(c.weights); flash("Pesos aplicados"); } catch (error) { onError(error); } }}>Aplicar y recalcular</button>
      </section>

      <section className="m-card">
        <h2>Agente de IA</h2>
        <p className="m-sub">Usa tu propia clave: pagas al proveedor por lo que uses. La clave se guarda en tu equipo con permisos privados y nunca vuelve al navegador.</p>
        <label>Proveedor
          <select value={provider} onChange={(e) => pickProvider(e.target.value)}>
            {Object.keys(agent.providers).map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label>Modelo<input value={model} onChange={(e) => setModel(e.target.value)} /></label>
        <label>Clave de API {agent.has_key && provider === agent.provider && <b>(guardada)</b>}
          <input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={agent.has_key ? "Dejar vacío para conservar" : "sk-…"} />
        </label>
        <label>Tope mensual de tokens
          <input type="number" min={1000} step={50000} value={cap} onChange={(e) => setCap(Number(e.target.value))} />
        </label>
        <p className="m-sub">Usado este mes: {agent.tokens_used_this_month.toLocaleString("es-PE")} de {agent.monthly_token_cap.toLocaleString("es-PE")}.</p>
        <button className="m-primary" onClick={saveAgent}>Guardar agente</button>
      </section>

      <section className="m-card">
        <h2>Más herramientas</h2>
        <p className="m-sub">Mapa de distritos y radios, análisis SQL y CVs objetivo.</p>
        <a className="m-primary m-linkbtn" href="/radar">Abrir modo avanzado</a>
        {authRequired && <button className="m-link" onClick={onLogout}>Cerrar sesión</button>}
      </section>
    </div>
  );
}
