"use client";

import { memo } from "react";
import { createPortal } from "react-dom";
import ChatTitle from "./ChatTitle";
import AgentChatPanel from "./AgentChatPanel";
import { useAgentChat } from "./useAgentChat";
import type { AgentContext } from "../../lib/mobile-api";

function AgentWindowBody({ onError, dock, onClose, context, titleSlot }: { onError: (e: unknown) => void; dock: { pinned: boolean; toggle: () => void }; onClose: () => void; context?: AgentContext; titleSlot?: HTMLElement | null }) {
  const chat = useAgentChat(onError, context);
  return (
    <div className="agent-body">
      {titleSlot && createPortal(<ChatTitle title={chat.title} onRename={chat.rename} />, titleSlot)}
      <AgentChatPanel chat={chat} context={context} dock={dock} onClose={onClose} onSettings={() => { window.location.href = "/ajustes"; }} />
    </div>
  );
}

export default memo(AgentWindowBody);
