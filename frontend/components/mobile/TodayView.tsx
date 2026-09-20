"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type SkillImpact, type Today, type TodayJob } from "../../lib/mobile-api";

function ago(iso: string | null): string {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  return days <= 0 ? "hoy" : days === 1 ? "ayer" : `hace ${days} d`;
}

export default function TodayView({ onSetup, onError }: { onSetup: () => void; onError: (e: unknown) => void }) {
  const [today, setToday] = useState<Today | null>(null);
  const [impact, setImpact] = useState<SkillImpact | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [t, i] = await Promise.all([api.today(), api.impact()]);
      setToday(t); setImpact(i);
    } catch (error) { onError(error); }
  }, [onError]);
  useEffect(() => { void load(); }, [load]);

  const act = async (job: TodayJob, action: "save" | "hide" | "star") => {
    setBusy(job.id);
    try {
      if (action === "save") await api.setApplication(job.id, "saved");
      if (action === "hide") await api.hide(job.id);
      if (action === "star") await api.favorite(job.id, !job.is_favorite);
      if (action === "star") setToday((t) => t && { ...t, jobs: t.jobs.map((j) => j.id === job.id ? { ...j, is_favorite: !j.is_favorite } : j) });
      else setToday((t) => t && { ...t, jobs: t.jobs.filter((j) => j.id !== job.id) });
    } catch (error) { onError(error); } finally { setBusy(null); }
  };

  if (!today) return <p className="m-empty">Cargando…</p>;
  return (
    <div className="m-stack">
      <header className="m-head"><h1>Hoy</h1><p>Ofertas frescas que encajan contigo</p></header>
      {!today.profile_configured && (
        <button className="m-callout" onClick={onSetup}>
          <strong>Configura tu perfil</strong>
          <span>Con tus skills verás por qué encaja cada oferta y qué te falta. Toca para empezar.</span>
        </button>
      )}
      {today.jobs.length === 0 && <p className="m-empty">Nada nuevo por ahora. Actualiza el mercado desde tu PC o pide al agente que busque.</p>}
      {today.jobs.map((job) => (
        <article className="m-card" key={job.id}>
          <div className="m-card-top">
            <div>
              <h2>{job.title}</h2>
              <p className="m-sub">{[job.company, job.location, ago(job.published_at)].filter(Boolean).join(" · ")}</p>
            </div>
            {job.score !== null && <span className="m-score" aria-label={`Encaje ${Math.round(job.score)} por ciento`}>{Math.round(job.score)}%</span>}
          </div>
          <p className="m-why">{job.why}</p>
          <div className="m-actions">
            <button disabled={busy === job.id} onClick={() => act(job, "save")}>Guardar</button>
            <button aria-pressed={job.is_favorite} disabled={busy === job.id} onClick={() => act(job, "star")}>{job.is_favorite ? "★" : "☆"}</button>
            <button disabled={busy === job.id} onClick={() => act(job, "hide")}>No me interesa</button>
            {job.url && <a href={job.url} target="_blank" rel="noopener noreferrer">Abrir ↗</a>}
          </div>
        </article>
      ))}
      {impact?.profile_configured && impact.skills.length > 0 && (
        <section className="m-card">
          <h2>Qué aprender primero</h2>
          <p className="m-sub">Simulación: cuánto sube tu encaje si dominas la skill (nivel básico), sobre {impact.jobs_considered} ofertas.</p>
          <ul className="m-list">
            {impact.skills.map((s) => (
              <li key={s.skill}><strong>{s.skill}</strong><span>+{s.avg_gain} pts en {s.jobs} ofertas{s.crossing ? ` · ${s.crossing} pasan a encaje alto` : ""}</span></li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
