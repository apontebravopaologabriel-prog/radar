"use client";

import "../perf.css";
import AuthGate from "../../components/AuthGate";
import AgentDock from "../../components/agent/AgentDock";
import FirstRun from "../../components/mobile/FirstRun";
import RadarClient from "../../components/RadarClient";
import { useState } from "react";
import type { AgentContext } from "../../lib/mobile-api";

export default function RadarPage() {
  const [agentContext, setAgentContext] = useState<AgentContext>({ screen: "map", mode: "districts" });
  return (
    <AuthGate>
      <div className="radar-stage">
        <RadarClient onAgentContextChange={setAgentContext} />
      </div>
      <FirstRun />
      <AgentDock context={agentContext} />
    </AuthGate>
  );
}
