"use client";

import { useEffect, useState } from "react";
import { api, type McpClient } from "../../lib/mobile-api";

/** «Conectar un cliente de IA»: muestra la configuración del servidor MCP de Radar y la instala con un clic confirmado. */
export default function McpConnect({ onError }: { onError: (e: unknown) => void }) {
  const [clients, setClients] = useState<McpClient[]>([]);
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => { api.mcpConfig().then((c) => { setClients(c.clients); setNote(c.note); }).catch(onError); }, [onError]);
  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); setMessage("Copiado."); } catch { setMessage("No se pudo copiar; selecciona el texto a mano."); }
  };
  const install = async (id: string) => {
    try {
      const result = await api.mcpInstall(id);
      setConfirming(null);
      setMessage(`Listo. ${result.restart}${result.backup ? ` Copia del archivo anterior: ${result.backup}` : ""}`);
      setClients((await api.mcpConfig()).clients);
    } catch (e) { onError(e); }
  };
  return (
    <section className="set-section">
      <h2>Conectar un cliente de IA</h2>
      <p className="m-sub">Radar incluye un servidor MCP para que Claude, Cursor o Gemini CLI consulten tus ofertas, tu perfil y tus brechas. {note}</p>
      <p className="m-sub">Todo lo que escribe pide tu confirmación en el cliente, y no existen herramientas que postulen o envíen mensajes.</p>
      {clients.map((client) => (
        <details key={client.id} className="set-advanced">
          <summary>{client.label}{client.exists ? " (ya tiene configuración)" : ""}</summary>
          {client.can_install ? (<>
            <p className="m-sub">Archivo: <code>{client.config_file}</code></p>
            <pre className="m-code">{client.snippet}</pre>
            <button type="button" onClick={() => void copy(client.snippet ?? "")}>Copiar configuración</button>{" "}
            {confirming === client.id
              ? <><button className="m-primary" type="button" onClick={() => void install(client.id)}>Sí, escribir en ese archivo</button>{" "}<button type="button" onClick={() => setConfirming(null)}>Cancelar</button></>
              : <button className="m-primary" type="button" onClick={() => setConfirming(client.id)}>Instalar en {client.label}</button>}
          </>) : (<>
            <pre className="m-code">{client.command}</pre>
            <button type="button" onClick={() => void copy(client.command ?? "")}>Copiar comando</button>
          </>)}
        </details>
      ))}
      {message && <p className="m-sub" role="status">{message}</p>}
    </section>
  );
}
