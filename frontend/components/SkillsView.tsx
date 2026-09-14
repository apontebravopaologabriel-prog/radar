"use client";

import { useMemo, useState } from "react";
import type { SkillDemand, SkillOverview, SkillSnapshot } from "../types";

type Props = { data: SkillOverview | null; history: SkillSnapshot[]; loading: boolean; error: string | null; selectedName: string | null; onSelectSkill: (name: string | null) => void };
type Tab = "ranking" | "evolution";
type Kind = "all" | SkillDemand["skill_type"];
const kindLabels: Record<Exclude<Kind, "all">, string> = { technical: "Técnicas", methodology: "Metodologías", domain: "Dominio", language: "Idiomas", soft: "Blandas" };
const kindColors: Record<Exclude<Kind, "all">, string> = { technical: "#63d7c0", methodology: "#f0bb62", domain: "#a59bff", language: "#8ba7a0", soft: "#ef8d72" };
function demandLabel(skill: SkillDemand) { return skill.share >= 0.35 ? "Alta" : skill.share >= 0.12 ? "Media" : "Emergente"; }
function formatMonth(date: string) { return new Intl.DateTimeFormat("es-PE", { month: "short", year: "2-digit" }).format(new Date(`${date}T00:00:00`)); }

export default function SkillsView({ data, history, loading, error, selectedName, onSelectSkill }: Props) {
  const [tab, setTab] = useState<Tab>("ranking");
  const [kind, setKind] = useState<Kind>("all");
  const skills = data?.skills || [];
  const filtered = skills.filter((skill) => kind === "all" || skill.skill_type === kind);
  const selected = skills.find((skill) => skill.name === selectedName) || null;
  const latestBySkill = useMemo(() => new Map(history.map((point) => [point.skill, point])), [history]);
  return <div className="skills-view">
    <div className="skills-header"><div><p className="eyebrow">Inteligencia del mercado</p><h2>Demanda de competencias <span>// habilidades ↔ ofertas</span></h2></div><div className="skills-summary"><strong>{data?.total_jobs || 0}</strong><span>ofertas analizadas · {data?.max_age_days || 30} días</span></div></div>
    <nav className="skills-tabs" aria-label="Vistas de demanda">{([['ranking', 'Ranking'], ['evolution', 'Evolución']] as const).map(([value, label]) => <button key={value} type="button" className={tab === value ? "active" : ""} onClick={() => setTab(value)}>{label}</button>)}</nav>
    <div className="skill-kind-filter" role="group" aria-label="Tipo de competencia"><button type="button" className={kind === "all" ? "active" : ""} onClick={() => setKind("all")}>Todas</button>{(Object.keys(kindLabels) as Exclude<Kind, "all">[]).map((value) => <button key={value} type="button" className={kind === value ? "active" : ""} onClick={() => setKind(value)}><i style={{ background: kindColors[value] }} />{kindLabels[value]}</button>)}</div>
    {loading && <div className="skills-loading">Analizando demanda laboral…</div>}{!loading && error && <div className="skills-loading error-state">{error}</div>}
    {!loading && !error && tab === "ranking" && <section className="skills-ranking"><div className="skills-ranking-head"><span>Competencia</span><span>Ofertas</span><span>Participación</span><span>Requisito</span></div>{filtered.map((skill) => <button type="button" key={skill.name} className={`skills-ranking-row ${selectedName === skill.name ? "selected" : ""}`} onClick={() => onSelectSkill(selectedName === skill.name ? null : skill.name)}><strong><i style={{ background: kindColors[skill.skill_type] }} />{skill.name}</strong><span>{skill.job_count}</span><i><em style={{ width: `${Math.max(3, skill.share * 100)}%` }} /></i><span>{Math.round(skill.share * 100)}%</span><small>{skill.required_count} requeridas</small></button>)}{selected && <SkillDetail skill={selected} latest={latestBySkill.get(selected.name)} />}</section>}
    {!loading && !error && tab === "evolution" && <section className="skills-evolution"><div className="evolution-heading"><div><p className="eyebrow">Snapshots guardados</p><h3>Cómo cambia la demanda</h3></div><span>{history.length ? `${new Set(history.map((point) => point.date)).size} fechas disponibles` : "Sin histórico todavía"}</span></div>{history.length ? <div className="evolution-list">{filtered.slice(0, 12).map((skill) => { const points = history.filter((point) => point.skill === skill.name); const first = points[0]?.value ?? skill.job_count; const last = points[points.length - 1]?.value ?? skill.job_count; const change = first ? Math.round(((last - first) / first) * 100) : 0; return <button type="button" key={skill.name} className="evolution-row" onClick={() => onSelectSkill(selectedName === skill.name ? null : skill.name)}><strong>{skill.name}</strong><div className="evolution-track">{points.slice(-12).map((point) => <i key={`${point.date}-${point.skill}`} title={`${formatMonth(point.date)}: ${point.value}`} style={{ height: `${Math.max(8, (point.value / Math.max(last, 1)) * 100)}%` }} />)}</div><span>{last} <b className={change >= 0 ? "up" : "down"}>{change >= 0 ? "+" : ""}{change}%</b></span></button>; })}</div> : <div className="skills-empty-history">Aún no hay snapshots de skills. Ejecuta la captura de mercado para empezar a comparar meses.</div>}</section>}
  </div>;
}

function SkillDetail({ skill, latest }: { skill: SkillDemand; latest?: SkillSnapshot }) {
  const guidance = skill.skill_type === "soft" ? "Evalúa esta competencia con ejemplos concretos de coordinación, decisiones o resultados; una mención en la oferta no demuestra dominio." : skill.skill_type === "language" ? "Comprueba el nivel solicitado y prepara una evidencia práctica, como una conversación o un entregable." : "Prioriza esta competencia cuando aparezca repetidamente en ofertas objetivo y valida el nivel con un proyecto o entregable.";
  return <aside className="skill-detail-panel"><p className="eyebrow">Competencia seleccionada</p><h3>{skill.name}</h3><span className="skill-category" style={{ borderColor: kindColors[skill.skill_type] }}>{kindLabels[skill.skill_type]} · {skill.category}</span><div className="skill-detail-grid"><div><span>Demanda</span><strong>{demandLabel(skill)}</strong></div><div><span>Ofertas</span><strong>{skill.job_count}</strong></div><div><span>Participación</span><strong>{Math.round(skill.share * 100)}%</strong></div><div><span>Requerida</span><strong>{skill.required_count}</strong></div></div><div className="skill-market-note"><span>Lectura de mercado</span><p>{skill.name} aparece en {skill.job_count} ofertas dentro de la ventana actual. {skill.required_count ? `${skill.required_count} la marcan como requisito explícito.` : "La mayoría de menciones no está marcada como requisito obligatorio."}</p></div>{latest && <div className="skill-market-note"><span>Último snapshot</span><p>{formatMonth(latest.date)} · {latest.value} ofertas registradas.</p></div>}<div className="skill-market-note skill-advice"><span>Qué hacer con este dato</span><p>{guidance}</p></div></aside>;
}
