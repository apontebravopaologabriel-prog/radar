"use client";

import { useEffect, useState, type ReactNode } from "react";
import "./mobile/mobile.css";
import { api } from "../lib/mobile-api";

type State = "checking" | "open" | "login" | "offline";

/** Pantalla de acceso para el escritorio: solo aparece si el servidor tiene `RADAR_ACCESS_TOKEN` y no hay sesión. */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>("checking");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    api.authStatus()
      .then((status) => setState(status.required && !status.authenticated ? "login" : "open"))
      .catch(() => setState("offline"));
  }, []);
  const login = async () => {
    try {
      await api.login(token);
      setToken(""); setError(""); setState("open");
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo iniciar sesión"); }
  };
  if (state === "open") return <>{children}</>;
  if (state === "checking") return null;
  return (
    <div className="m-app"><main className="m-main m-login">
      <span className="m-eyebrow">[ACCESO]</span><h1>Radar</h1>
      {state === "offline" ? <p className="m-sub" role="alert">No se pudo contactar a Radar. ¿Está encendido?</p> : (<>
        <p className="m-sub">Ingresa tu clave de acceso.</p>
        <form onSubmit={(e) => { e.preventDefault(); void login(); }}>
          <input type="password" autoComplete="current-password" value={token} onChange={(e) => setToken(e.target.value)} aria-label="Clave de acceso" />
          <button className="m-primary" type="submit" disabled={!token}>Entrar</button>
        </form>
      </>)}
      {error && <p className="m-toast" role="alert">{error}</p>}
    </main></div>
  );
}
