"use client";

import { useMemo, useState } from "react";
import type { SkillDemand, SkillOverview } from "../types";

type Props = { data: SkillOverview | null; loading: boolean; error: string | null };

const ROADMAP = [
  { title: "Fundamentos", skills: ["Excel", "SQL", "Python"] },
  { title: "Analítica aplicada", skills: ["Power BI", "PostgreSQL", "Optimization", "Forecasting"] },
  { title: "Operaciones digitales", skills: ["SAP", "Inventory Management", "Supply Chain"] },
  { title: "Siguiente frontera", skills: ["ETL", "APIs", "Airflow", "Cloud"] },
];

function levelLabel(level: SkillDemand["user_level"]) {
  return { none: "No iniciado", basic: "Básico", intermediate: "En práctica", advanced: "Avanzado" }[level];
}

function demandLabel(skill: SkillDemand) {
  if (skill.share >= 0.35) return "Alta";
  if (skill.share >= 0.12) return "Media";
  return "Emergente";
}

function progress(level: SkillDemand["user_level"]) {
  return ({ none: 0, basic: 33, intermediate: 66, advanced: 100 } as Record<string, number>)[level];
}

function competencyGuidance(name: string, category: string) {
  const normalized = name.toLowerCase();
  if (normalized.includes("excel")) {
    return { human: "Modelar, validar e interpretar datos.", ai: "Fórmulas, Power Query y automatización.", evidence: "Un dashboard con conclusiones ejecutivas." };
  }
  if (normalized.includes("sql") || normalized.includes("postgres")) {
    return { human: "Diseñar consultas, relaciones y controles de calidad.", ai: "Borradores de consultas, optimización y documentación.", evidence: "Un análisis reproducible con modelo y consultas explicadas." };
  }
  if (normalized.includes("power bi") || normalized.includes("tableau")) {
    return { human: "Elegir indicadores y comunicar decisiones.", ai: "Medidas, visualizaciones y revisión de consistencia.", evidence: "Un tablero conectado a una recomendación de negocio." };
  }
  if (category === "soft" || category === "communication") {
    return { human: "Explicar decisiones, coordinar y recibir feedback.", ai: "Preparar guiones, simulaciones y retroalimentación.", evidence: "Una presentación o retrospectiva con feedback." };
  }
  return { human: `Comprender ${name}, aplicarlo y verificar sus resultados.`, ai: "Investigación, borradores y automatización supervisada.", evidence: `Un proyecto pequeño donde ${name} resuelva un problema real.` };
}

function gapLabel(skill: SkillDemand) {
  const expected = skill.share >= 0.35 ? 2 : skill.share >= 0.12 ? 1 : 0;
  const actual = progress(skill.user_level) / 33;
  if (actual >= expected && actual > 0) return "Cubierta";
  if (actual > 0) return "En desarrollo";
  return "Brecha";
}

export default function SkillsView({ data, loading, error }: Props) {
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const skills = data?.skills || [];
  const topSkills = skills.slice(0, 12);
  const selected = skills.find((skill) => skill.name === selectedName) || null;
  const skillByName = useMemo(() => new Map(skills.map((skill) => [skill.name, skill])), [skills]);
  const maxCount = topSkills[0]?.job_count || 1;

  return (
    <div className="skills-view">
      <div className="skills-header">
        <div>
          <p className="eyebrow">Mapa de capacidades</p>
          <h2>Competencias <span>// demanda + evidencia</span></h2>
        </div>
        <div className="skills-summary"><strong>{data?.total_jobs || 0}</strong><span>ofertas analizadas · {data?.max_age_days || 30} días</span></div>
      </div>

      {loading && <div className="skills-loading">Construyendo mapa de habilidades…</div>}
      {!loading && error && <div className="skills-loading error-state">{error}</div>}
      {!loading && !error && <div className="skills-layout">
        <section className="skills-graph-panel" aria-label="Mapa de habilidades demandadas">
          <div className="skills-graph">
            <svg viewBox="0 0 640 460" role="img" aria-label="Conexiones entre tu perfil y las habilidades más demandadas">
              {topSkills.map((skill, index) => {
                const angle = (-Math.PI / 2) + (index / Math.max(topSkills.length, 1)) * Math.PI * 2;
                const x = 320 + Math.cos(angle) * 170;
                const y = 230 + Math.sin(angle) * 155;
                return <line key={`line-${skill.name}`} x1="320" y1="230" x2={x} y2={y} className="skill-edge" />;
              })}
              <circle cx="320" cy="230" r="54" className="skill-core" />
              <text x="320" y="224" className="skill-core-label" textAnchor="middle">MI PERFIL</text>
              <text x="320" y="242" className="skill-core-sub" textAnchor="middle">demanda real</text>
              {topSkills.map((skill, index) => {
                const angle = (-Math.PI / 2) + (index / Math.max(topSkills.length, 1)) * Math.PI * 2;
                const x = 320 + Math.cos(angle) * 170;
                const y = 230 + Math.sin(angle) * 155;
                const radius = 13 + Math.round((skill.job_count / maxCount) * 17);
                const isSelected = selectedName === skill.name;
                return <g key={skill.name} className={`skill-node ${isSelected ? "selected" : ""} level-${skill.user_level}`} onClick={() => setSelectedName(skill.name)} role="button" tabIndex={0} aria-label={`${skill.name}, ${skill.job_count} ofertas`} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setSelectedName(skill.name); }}>
                  <circle cx={x} cy={y} r={radius} />
                  <text x={x} y={y + radius + 15} textAnchor="middle">{skill.name}</text>
                  <text x={x} y={y + 4} className="skill-node-count" textAnchor="middle">{skill.job_count}</text>
                </g>;
              })}
            </svg>
          </div>
          <div className="skills-legend"><span><i className="legend-owned" /> Mi nivel</span><span><i className="legend-demand" /> Demanda</span><span><i className="legend-gap" /> Brecha</span></div>
          <p className="skills-note">El tamaño representa ofertas distintas. Selecciona un nodo para separar lo que debes comprender de lo que la IA puede asistir.</p>
        </section>

        <aside className="skill-detail-panel">
          {selected ? <>
            <p className="eyebrow">Skill seleccionada</p>
            <h3>{selected.name}</h3>
            <span className="skill-category">{selected.category}</span>
            <div className="skill-detail-grid"><div><span>Demanda</span><strong>{demandLabel(selected)}</strong></div><div><span>Ofertas</span><strong>{selected.job_count} <small>({Math.round(selected.share * 100)}%)</small></strong></div><div><span>Nivel declarado</span><strong>{levelLabel(selected.user_level)}</strong></div><div><span>Brecha</span><strong className={`gap-${gapLabel(selected).toLowerCase().replace(" ", "-")}`}>{gapLabel(selected)}</strong></div></div>
            <div className="skill-progress"><div><span>Progreso declarado</span><b>{progress(selected.user_level)}%</b></div><i><em style={{ width: `${progress(selected.user_level)}%` }} /></i></div>
            {(() => { const guidance = competencyGuidance(selected.name, selected.category); return <div className="competency-guidance"><div><span>Debe dominar el humano</span><strong>{guidance.human}</strong></div><div><span>La IA puede asistir</span><strong>{guidance.ai}</strong></div></div>; })()}
            <p className="skill-next"><strong>Siguiente evidencia</strong>{selected.user_level === "advanced" ? "Documenta un caso real y úsalo como evidencia profesional." : competencyGuidance(selected.name, selected.category).evidence}</p>
            {selected.evidence && <p className="skill-evidence">“{selected.evidence}”</p>}
          </> : <div className="skill-detail-empty"><span>◎</span><strong>Selecciona una skill</strong><p>Elige un nodo para comparar la demanda del mercado con tu progreso.</p></div>}
        </aside>
      </div>}

      {!loading && !error && <section className="roadmap-section"><div className="roadmap-heading"><div><p className="eyebrow">Ruta sugerida</p><h3>Ingeniería Industrial Digital</h3></div><span>Progreso basado en evidencia</span></div><div className="roadmap-track">{ROADMAP.map((stage, index) => { const stageSkills = stage.skills.map((name) => skillByName.get(name)).filter(Boolean) as SkillDemand[]; const done = stageSkills.filter((skill) => skill.user_level === "advanced").length; return <div className="roadmap-stage" key={stage.title}><div className="roadmap-stage-top"><b>0{index + 1}</b><strong>{stage.title}</strong><span>{done}/{stage.skills.length}</span></div><div className="roadmap-stage-skills">{stage.skills.map((name) => { const skill = skillByName.get(name); return <button key={name} type="button" className={`roadmap-skill ${skill?.user_level || "none"}`} onClick={() => setSelectedName(name)}>{name}<i>{skill ? `${skill.job_count} ofertas` : "por explorar"}</i></button>; })}</div></div>; })}</div></section>}
    </div>
  );
}
