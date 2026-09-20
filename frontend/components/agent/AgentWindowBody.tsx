"use client";

import { memo } from "react";
import AgentChatPanel from "./AgentChatPanel";
import { useAgentChat } from "./useAgentChat";
import type { AgentContext } from "../../lib/mobile-api";

function AgentWindowBody({ onError, dock, onClose, context }: { onError: (e: unknown) => void; dock: { pinned: boolean; toggle: () => void }; onClose: () => void; context?: AgentContext }) {
  const chat = useAgentChat(onError, context);
  return (
    <div className="agent-body">
      <AgentChatPanel chat={chat} context={context} dock={dock} onClose={onClose} onSettings={() => { window.location.href = "/ajustes"; }} />
    </div>
  );
}

export default memo(AgentWindowBody);
