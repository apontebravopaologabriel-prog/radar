/** Símbolo del agente de Radar: anillo, barrido y punto. Gira mientras el agente trabaja. */
export default function RadarMark({ spinning = false, intro = false, size = 14 }: { spinning?: boolean; intro?: boolean; size?: number }) {
  return (
    <svg className={`radar-mark ${spinning ? "is-spinning" : ""}${intro ? " is-intro" : ""}`} width={size} height={size} viewBox="0 0 16 16" role="img" aria-label="Agente de Radar">
      <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.2" opacity=".55" />
      <circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" strokeWidth="1.2" opacity=".85" />
      <g className="radar-mark-sweep"><path d="M8 8 13.2 2.8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /><circle cx="13.2" cy="2.8" r="1.3" fill="currentColor" /></g>
    </svg>
  );
}
