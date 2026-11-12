"use client";

import AgentChatPanel from "../agent/AgentChatPanel";
import ChatTitle from "../agent/ChatTitle";
import { useAgentChat } from "../agent/useAgentChat";
import type { AgentContext } from "../../lib/mobile-api";

export default function AgentView({ onSettings, onError, context }: { onSettings: () => void; onError: (e: unknown) => void; context?: AgentContext }) {
  const chat = useAgentChat(onError, context);
  const { settings, lines, reset } = chat;
  const cap = settings?.monthly_token_cap ?? 0;
  const used = settings?.tokens_used_this_month ?? 0;
  return (
    <div className="m-chat-page">
      <header className="m-head m-head-row">
        <div><span className="m-eyebrow">[AGENTE]</span><h1>Agente</h1><p className="m-chat-title"><ChatTitle title={chat.title} onRename={chat.rename} /></p>{settings && <p>{settings.ready ? `${settings.model} · ${Math.round((used / Math.max(cap, 1)) * 100)}% del tope mensual` : "Sin configurar"}</p>}</div>
        {lines.length > 0 && <button className="m-link" onClick={reset}>Nueva</button>}
      </header>
      <AgentChatPanel chat={chat} onSettings={onSettings} />
    </div>
  );
}
