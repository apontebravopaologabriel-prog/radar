"use client";
import { useCallback } from "react";
import ProcessesView from "../ProcessesView";
import type { AgentContext } from "../../lib/mobile-api";
export default function PipelineView({ onContextChange }: { onError: (e: unknown) => void; onContextChange?: (context: AgentContext) => void }) {
  const context = useCallback((count: number, status: string) => onContextChange?.({ screen: "pipeline", visibleCount: count, filters: { status } }), [onContextChange]);
  return <ProcessesView onContextChange={context} />;
}
