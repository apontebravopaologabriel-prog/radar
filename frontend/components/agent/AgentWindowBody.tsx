"use client";

import AgentChatPanel from "./AgentChatPanel";
import { useAgentChat } from "./useAgentChat";

export default function AgentWindowBody({ onError }: { onError: (e: unknown) => void }) {
  const chat = useAgentChat(onError);
  const { settings, lines, reset } = chat;
  const cap = settings?.monthly_token_cap ?? 0;
  const used = settings?.tokens_used_this_month ?? 0;
  return (
    <div className="agent-body">
      <div className="agent-meta">
        <span>{settings?.ready ? `${settings.model} · ${Math.round((used / Math.max(cap, 1)) * 100)}% del tope` : "Sin configurar"}{settings?.read_only ? " · solo lectura" : ""}</span>
        {lines.length > 0 && <button type="button" className="m-link" onClick={reset}>Nueva</button>}
      </div>
      <AgentChatPanel chat={chat} onSettings={() => { window.location.href = "/ajustes"; }} />
    </div>
  );
}
