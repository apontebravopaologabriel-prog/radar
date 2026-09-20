"use client";

import AgentChatPanel from "./AgentChatPanel";
import { useAgentChat } from "./useAgentChat";

export default function AgentWindowBody({ onError, dock, onClose }: { onError: (e: unknown) => void; dock: { pinned: boolean; toggle: () => void }; onClose: () => void }) {
  const chat = useAgentChat(onError);
  return (
    <div className="agent-body">
      <AgentChatPanel chat={chat} dock={dock} onClose={onClose} onSettings={() => { window.location.href = "/ajustes"; }} />
    </div>
  );
}
