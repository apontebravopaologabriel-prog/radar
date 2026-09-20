"use client";

import AgentChatPanel from "../agent/AgentChatPanel";
import { useAgentChat } from "../agent/useAgentChat";

export default function AgentView({ onSettings, onError }: { onSettings: () => void; onError: (e: unknown) => void }) {
  const chat = useAgentChat(onError);
  const { settings, lines, reset } = chat;
  const cap = settings?.monthly_token_cap ?? 0;
  const used = settings?.tokens_used_this_month ?? 0;
  return (
    <div className="m-chat-page">
      <header className="m-head m-head-row">
        <div><span className="m-eyebrow">[AGENTE]</span><h1>Agente</h1>{settings && <p>{settings.ready ? `${settings.model} · ${Math.round((used / Math.max(cap, 1)) * 100)}% del tope mensual` : "Sin configurar"}</p>}</div>
        {lines.length > 0 && <button className="m-link" onClick={reset}>Nueva</button>}
      </header>
      <AgentChatPanel chat={chat} onSettings={onSettings} />
    </div>
  );
}
