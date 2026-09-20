"use client";

import { useCallback, useState } from "react";
import "./mobile.css";
import SettingsView from "./SettingsView";

/** Ajustes a pantalla completa para el escritorio (mismo contenido que la pestaña móvil). */
export default function SettingsPage() {
  const [error, setError] = useState("");
  const onError = useCallback((e: unknown) => setError(e instanceof Error ? e.message : "Error desconocido"), []);
  return (
    <div className="m-app">
      <main className="m-main">
        <a className="m-link" href="/radar">← Volver al mapa</a>
        <SettingsView authRequired={false} onLogout={() => undefined} onError={onError} />
      </main>
      {error && <p className="m-toast" role="alert" onClick={() => setError("")}>{error}</p>}
    </div>
  );
}
