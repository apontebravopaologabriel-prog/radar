"use client";

import { useCallback, useEffect, useState } from "react";
import { api, AuthRequired } from "../../lib/mobile-api";
import "./mobile.css";
import AgentView from "./AgentView";
import Onboarding from "./Onboarding";
import PipelineView from "./PipelineView";
import SettingsView from "./SettingsView";
import TodayView from "./TodayView";

type Tab = "today" | "pipeline" | "agent" | "settings";
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "today", label: "Hoy", icon: "◉" },
  { id: "pipeline", label: "Seguimiento", icon: "☰" },
  { id: "agent", label: "Agente", icon: "✦" },
  { id: "settings", label: "Ajustes", icon: "⚙" },
];

export default function MobileApp() {
  const [auth, setAuth] = useState<{ required: boolean; authenticated: boolean } | null>(null);
  const [tab, setTab] = useState<Tab>("today");
  const [setup, setSetup] = useState(false);
  const [error, setError] = useState("");
  const [token, setToken] = useState("");
  const [epoch, setEpoch] = useState(0); // fuerza recarga de las vistas tras cambios de perfil

  const onError = useCallback((e: unknown) => {
    if (e instanceof AuthRequired) setAuth({ required: true, authenticated: false });
    else setError(e instanceof Error ? e.message : "Error desconocido");
  }, []);

  useEffect(() => {
    api.authStatus().then(setAuth).catch(() => setError("No se pudo contactar a Radar. ¿Está encendido?"));
    const hash = window.location.hash.slice(1) as Tab;
    if (TABS.some((t) => t.id === hash)) setTab(hash);
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }, []);
  useEffect(() => { if (window.location.hash.slice(1) !== tab) history.replaceState(null, "", `#${tab}`); }, [tab]);
  useEffect(() => { if (!error) return; const t = setTimeout(() => setError(""), 5000); return () => clearTimeout(t); }, [error]);

  const login = async () => {
    try { await api.login(token); setToken(""); setAuth(await api.authStatus()); } catch (e) { setError(e instanceof Error ? e.message : "No se pudo iniciar sesión"); }
  };
  const logout = async () => {
    await api.logout().catch(() => undefined);
    if ("caches" in window) await caches.delete("radar-api-v1");
    try { localStorage.removeItem("radar.chat.v1"); } catch { /* sin almacenamiento */ }
    setAuth(await api.authStatus());
  };

  if (!auth) return <div className="m-app"><p className="m-empty">{error || "Cargando…"}</p></div>;
  if (auth.required && !auth.authenticated) {
    return (
      <div className="m-app"><main className="m-main m-login">
        <h1>Radar</h1><p className="m-sub">Ingresa tu clave de acceso.</p>
        <form onSubmit={(e) => { e.preventDefault(); void login(); }}>
          <input type="password" autoComplete="current-password" value={token} onChange={(e) => setToken(e.target.value)} aria-label="Clave de acceso" />
          <button className="m-primary" type="submit" disabled={!token}>Entrar</button>
        </form>
        {error && <p className="m-toast" role="alert">{error}</p>}
      </main></div>
    );
  }
  return (
    <div className="m-app">
      <main className="m-main">
        {setup ? (
          <Onboarding onError={onError} onDone={() => { setSetup(false); setEpoch((n) => n + 1); setTab("today"); }} />
        ) : tab === "today" ? <TodayView key={epoch} onSetup={() => setSetup(true)} onError={onError} />
        : tab === "pipeline" ? <PipelineView onError={onError} />
        : tab === "agent" ? <AgentView onSettings={() => setTab("settings")} onError={onError} />
        : <SettingsView authRequired={auth.required} onLogout={logout} onError={onError} />}
      </main>
      {error && <p className="m-toast" role="alert">{error}</p>}
      <nav className="m-tabs" aria-label="Secciones">
        {TABS.map((t) => (
          <button key={t.id} aria-current={!setup && tab === t.id ? "page" : undefined} onClick={() => { setSetup(false); setTab(t.id); }}>
            <span aria-hidden>{t.icon}</span>{t.label}
          </button>
        ))}
        <a href="/radar"><span aria-hidden>◎</span>Mapa</a>
      </nav>
    </div>
  );
}
