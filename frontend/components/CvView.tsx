"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { updateJobFavorite } from "../lib/api";
import { CV_PHOTO_URL, fetchCvProfile, fetchCvSelection, fetchCvTargets } from "../lib/cv-api";
import type { CvBaselineItem, CvGap, CvItem, CvMatrix, CvProfile, CvReadiness, CvSelectionItem, CvStatus, CvTarget } from "../lib/cv-types";
import "./cv.css";

const MAX_COMPARED = 4;
const STATUS_MARK: Record<CvStatus, string> = { cubierto: "✓", parcial: "~", falta: "✗" };
const STATUS_LABEL: Record<CvStatus, string> = { cubierto: "Cubierto", parcial: "Parcial", falta: "Falta" };
const STATUS_ORDER: Record<CvStatus, number> = { falta: 0, parcial: 1, cubierto: 2 };
const ORIGIN_LABEL: Record<CvItem["origin"], string> = { explicito: "explícito", inferido: "inferido", tipico: "típico" };
const KIND_LABEL: Record<CvGap["kind"], string> = { dias: "días", semanas: "semanas", no_cerrable_rapido: "no cierra rápido" };
const SECTION_LABEL: Record<string, string> = { summary: "Resumen", education: "Formación", experience: "Experiencia", tools: "Herramientas", certifications: "Certificaciones" };
const SECTION_ORDER = ["summary", "experience", "tools", "education", "certifications"];

type Tab = "objetivos" | "matriz" | "comparar" | "cv";

export default function CvView() {
  const [profile, setProfile] = useState<CvProfile | null>(null);
  const [selection, setSelection] = useState<CvSelectionItem[]>([]);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [details, setDetails] = useState<{ targets: CvTarget[]; matrix: CvMatrix | null }>({ targets: [], matrix: null });
  const [tab, setTab] = useState<Tab>("objetivos");
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const touchedPick = useRef(false);

  const loadSelection = useCallback(async (signal?: AbortSignal) => {
    const next = await fetchCvSelection(signal);
    setSelection(next);
    setCompareIds((current) => {
      const valid = current.filter((id) => next.some((item) => item.id === id));
      if (touchedPick.current) return valid;
      return next.filter((item) => !item.readiness.low_data).concat(next.filter((item) => item.readiness.low_data)).slice(0, 3).map((item) => item.id);
    });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchCvProfile(controller.signal), loadSelection(controller.signal)])
      .then(([nextProfile]) => { setProfile(nextProfile); setLoaded(true); })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "No se pudieron cargar los CVs");
        setLoaded(true);
      });
    return () => controller.abort();
  }, [loadSelection]);

  const idsKey = compareIds.join(",");
  useEffect(() => {
    if (!idsKey) { setDetails({ targets: [], matrix: null }); return; }
    const controller = new AbortController();
    fetchCvTargets(idsKey.split(","), controller.signal)
      .then((data) => setDetails(data))
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "No se pudo cargar el detalle"); });
    return () => controller.abort();
  }, [idsKey]);

  // El detalle de un objetivo abierto puede no estar entre los comparados: se pide aparte.
  const [openTarget, setOpenTarget] = useState<CvTarget | null>(null);
  useEffect(() => {
    if (!openId) { setOpenTarget(null); return; }
    const known = details.targets.find((target) => target.id === openId);
    if (known) { setOpenTarget(known); return; }
    const controller = new AbortController();
    fetchCvTargets([openId], controller.signal)
      .then((data) => setOpenTarget(data.targets[0] ?? null))
      .catch(() => { if (!controller.signal.aborted) setOpenTarget(null); });
    return () => controller.abort();
  }, [openId, details.targets]);

  function togglePick(id: string) {
    touchedPick.current = true;
    setCompareIds((current) => current.includes(id) ? current.filter((value) => value !== id) : current.length >= MAX_COMPARED ? current : [...current, id]);
  }

  async function removeTarget(id: string) {
    try {
      await updateJobFavorite(id, false);
      touchedPick.current = true;
      if (openId === id) { setOpenId(null); setTab("objetivos"); }
      await loadSelection();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo quitar el objetivo");
    }
  }

  function openTargetTab(id: string) { setOpenId(id); setTab("cv"); }

  return (
    <div className="cv-view">
      <header className="cv-profile">
        {/* eslint-disable-next-line @next/next/no-img-element -- export estático sin optimizador de imágenes */}
        {profile?.has_photo ? <img className="cv-photo" src={CV_PHOTO_URL} alt={`Foto de ${profile.name}`} /> : <div className="cv-photo cv-photo-empty" aria-hidden="true">∅</div>}
        <div className="cv-profile-text">
          <p className="eyebrow">CVs objetivo / hipotéticos</p>
          <h2>{profile?.name ?? "Perfil real no cargado"}</h2>
          {profile && <p className="cv-profile-meta">{[profile.home_district, profile.education?.[0] ? `${profile.education[0].program} (${profile.education[0].status})` : null].filter(Boolean).join(" · ")}</p>}
        </div>
        <nav className="cv-tabs" role="tablist" aria-label="Vista de CVs">
          {([["objetivos", `Objetivos (${selection.length})`], ["matriz", "Matriz"], ["comparar", "Comparar"]] as const).map(([value, label]) => (
            <button key={value} type="button" role="tab" aria-selected={tab === value} className={tab === value ? "active" : ""} onClick={() => setTab(value)}>{label}</button>
          ))}
          {openId && <button type="button" role="tab" aria-selected={tab === "cv"} className={tab === "cv" ? "active" : ""} onClick={() => setTab("cv")}>{openTarget?.company ?? "CV"}</button>}
        </nav>
      </header>
      <div className="cv-body">
        {error && <p className="cv-note">{error}</p>}
        {loaded && !error && selection.length === 0 && <p className="cv-note">Aún no hay objetivos. Marca ofertas con ★ en el mapa y aparecerán aquí, ordenadas por cercanía a tu perfil.</p>}
        {tab === "objetivos" && selection.length > 0 && <Ranking items={selection} picked={compareIds} onPick={togglePick} onOpen={openTargetTab} onRemove={(id) => void removeTarget(id)} />}
        {tab === "matriz" && (details.matrix && details.matrix.rows.length > 0 ? <MatrixTable matrix={details.matrix} onOpen={openTargetTab} /> : <p className="cv-note">Elige de 1 a {MAX_COMPARED} objetivos en la pestaña Objetivos.</p>)}
        {tab === "comparar" && (details.targets.length > 0 ? <CompareGrid profile={profile} targets={details.targets} /> : <p className="cv-note">Elige de 1 a {MAX_COMPARED} objetivos en la pestaña Objetivos.</p>)}
        {tab === "cv" && openTarget && <TargetCv target={openTarget} />}
      </div>
    </div>
  );
}

function Meter({ readiness }: { readiness: CvReadiness }) {
  if (readiness.percent === null || readiness.low_data) return <span className="cv-lowdata" title="La oferta aporta pocas señales; el porcentaje no sería fiable">datos insuficientes</span>;
  return (
    <span className="cv-rank-meter" title={`${readiness.covered} cubiertos · ${readiness.partial} parciales · ${readiness.missing} faltan`}>
      <span>{readiness.percent}% cercanía</span>
      <span className="cv-bar"><i style={{ width: `${readiness.percent}%` }} /></span>
    </span>
  );
}

function Ranking({ items, picked, onPick, onOpen, onRemove }: { items: CvSelectionItem[]; picked: string[]; onPick: (id: string) => void; onOpen: (id: string) => void; onRemove: (id: string) => void }) {
  return (
    <section aria-label="Objetivos">
      <p className="cv-note">Tus ofertas con ★, de la más a la menos alcanzable. La cercanía la calcula Radar por reglas contra tu perfil real; marca hasta {MAX_COMPARED} para la matriz y la comparación.</p>
      <ul className="cv-rank">
        {items.map((item) => (
          <li key={item.id} className={`cv-rank-row ${picked.includes(item.id) ? "picked" : ""}`}>
            <input type="checkbox" checked={picked.includes(item.id)} disabled={!picked.includes(item.id) && picked.length >= MAX_COMPARED} onChange={() => onPick(item.id)} aria-label={`Comparar ${item.company ?? item.title}`} />
            <div className="cv-rank-title">
              <strong>{item.company ?? "Empresa no indicada"}<span className="cv-chip">{item.has_enrichment ? "con ideal" : "solo base"}</span>{item.readiness.blockers > 0 && <span className="cv-chip block">{item.readiness.blockers} bloqueo{item.readiness.blockers > 1 ? "s" : ""}</span>}</strong>
              <small>{item.title}{item.location.km_from_home !== null ? ` · ${item.location.km_from_home} km` : ""}</small>
            </div>
            <Meter readiness={item.readiness} />
            <div className="cv-rank-actions">
              <button type="button" onClick={() => onOpen(item.id)}>Abrir</button>
              <button type="button" onClick={() => onRemove(item.id)} aria-label={`Quitar ${item.company ?? item.title} de objetivos`} title="Quitar ★ de esta oferta">✕</button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function MatrixTable({ matrix, onOpen }: { matrix: CvMatrix; onOpen: (id: string) => void }) {
  return (
    <section className="cv-matrix" aria-label="Matriz de brechas">
      <p className="cv-note">Ordenada por cuántos puestos dejan el requisito abierto. Clic en un puesto para abrir su detalle.</p>
      <table>
        <thead>
          <tr>
            <th scope="col">Requisito</th>
            {matrix.columns.map((column) => <th key={column.id} scope="col"><button type="button" onClick={() => onOpen(column.id)} title={column.title}>{column.company ?? column.title}</button></th>)}
            <th scope="col">Abiertos</th>
          </tr>
        </thead>
        <tbody>
          {matrix.rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">{row.label}</th>
              {matrix.columns.map((column) => {
                const status = row.cells[column.id];
                const byAgent = row.agent_cells.includes(column.id);
                return <td key={column.id} className={status ? `cv-cell ${status}` : "cv-cell none"} title={status ? `${STATUS_LABEL[status]}${byAgent ? " (asignado por el agente)" : " (calculado por Radar)"}` : "No aplica"}>{status ? STATUS_MARK[status] : "·"}{byAgent && <span className="cv-agent-mark">a</span>}</td>;
              })}
              <td className="cv-open-count">{row.open_count}/{matrix.columns.length}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="cv-legend"><span>✓ cubierto</span><span>~ parcial</span><span>✗ falta</span><span>· no aplica</span><span>ᵃ estado asignado por el agente</span></p>
    </section>
  );
}

function BaselineTable({ items }: { items: CvBaselineItem[] }) {
  const sorted = [...items].sort((a, b) => Number(b.blocker) - Number(a.blocker) || STATUS_ORDER[a.status] - STATUS_ORDER[b.status]);
  return (
    <table className="cv-baseline">
      <thead><tr><th>Requisito</th><th>Estado</th><th>Por qué</th></tr></thead>
      <tbody>
        {sorted.map((item) => (
          <tr key={item.key}>
            <td>{item.label}{item.blocker && <span className="cv-chip block">bloqueo</span>}</td>
            <td><b className={`cv-mark ${item.status}`}>{STATUS_MARK[item.status]}</b> {STATUS_LABEL[item.status]}</td>
            <td className="reason">{item.reason}{item.quote ? ` — “${item.quote}”` : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TargetCv({ target }: { target: CvTarget }) {
  return (
    <article className="cv-doc">
      <div className="cv-banner" role="note">HIPOTÉTICO — no enviar</div>
      <h3>{target.title}</h3>
      <p className="cv-doc-meta">{target.company}{target.location.job ? ` · ${target.location.job}` : ""}{target.location.km_from_home !== null ? ` · ${target.location.km_from_home} km desde ${target.location.home} (aprox.)` : ""}</p>
      <h4>Requisitos calculados por Radar</h4>
      {target.baseline.length > 0 ? <BaselineTable items={target.baseline} /> : <p className="cv-note">La oferta no aporta requisitos detectables.</p>}
      {target.soft_skills.length > 0 && <p className="cv-note">Habilidades blandas que menciona la oferta (no se puntúan): {target.soft_skills.join(", ")}.</p>}
      {!target.has_enrichment && <p className="cv-note">Sin candidato ideal. Pídeselo al agente: leerá esta oferta con <code>get_target_context</code> y guardará el resultado con <code>save_target_profile</code>.</p>}
      {target.aviso && <p className="cv-note">{target.aviso}</p>}
      {SECTION_ORDER.filter((name) => target.sections[name]?.length).map((name) => (
        <section key={name}>
          <h4>{SECTION_LABEL[name]}</h4>
          <ul>
            {target.sections[name].map((item, index) => (
              <li key={`${name}-${index}`}>
                {item.status && <b className={`cv-mark ${item.status}`} title={STATUS_LABEL[item.status]}>{STATUS_MARK[item.status]}</b>}
                <span>{item.text}</span>
                <small className="cv-origin">{ORIGIN_LABEL[item.origin]}</small>
                {item.status_source === "agente" && <small className="cv-origin">estado: agente</small>}
                {(item.quote || item.reason) && <em>{item.quote ? `“${item.quote}”` : item.reason}{item.quote && item.reason ? ` — ${item.reason}` : ""}</em>}
              </li>
            ))}
          </ul>
        </section>
      ))}
      {target.gaps.length > 0 && (
        <section>
          <h4>Cómo acercarte</h4>
          <ul className="cv-gaps">
            {target.gaps.map((gap, index) => (
              <li key={`${gap.item}-${index}`}>
                <span>{gap.item}</span>
                <small className={`cv-kind ${gap.kind}`}>{KIND_LABEL[gap.kind]}{gap.estimate_days ? ` · ~${gap.estimate_days} d` : ""}</small>
                <em>{gap.action}{gap.evidence_to_produce ? ` Evidencia: ${gap.evidence_to_produce}.` : ""}</em>
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}

function realColumn(profile: CvProfile | null): Record<string, string[]> {
  if (!profile) return {};
  return {
    summary: profile.summary ? [profile.summary] : [],
    experience: (profile.experience ?? []).map((job) => `${job.role} · ${job.company} (${job.from} – ${job.to})`),
    tools: Object.entries(profile.tools_declared_in_db ?? {}).filter(([name]) => !name.startsWith("_")).map(([name, level]) => `${name} (${level}, autodeclarado)`),
    education: (profile.education ?? []).map((school) => `${school.program} · ${school.institution} (${school.status})`),
    certifications: (profile.certifications ?? []).map((cert) => `${cert.name} · ${cert.date}`),
  };
}

function CompareGrid({ profile, targets }: { profile: CvProfile | null; targets: CvTarget[] }) {
  const real = realColumn(profile);
  const sections = SECTION_ORDER.filter((name) => (real[name]?.length ?? 0) > 0 || targets.some((target) => target.sections[name]?.length));
  const columns = `minmax(200px, 1fr) repeat(${targets.length}, minmax(200px, 1fr))`;
  return (
    <section className="cv-compare" aria-label="Comparar CVs objetivo">
      <p className="cv-note">Tu perfil real a la izquierda y los puestos elegidos a la derecha. Cada sección queda alineada; los requisitos de arriba los calcula Radar.</p>
      <div className="cv-compare-grid" style={{ gridTemplateColumns: columns }}>
        <div className="cv-compare-head real">Tú (real)</div>
        {targets.map((target) => <div key={target.id} className="cv-compare-head"><span className="cv-banner-inline">HIPOTÉTICO</span>{target.company}<small>{target.title}</small></div>)}
        <div className="cv-compare-row">
          <h4 className="cv-compare-section">Requisitos (Radar)</h4>
          <ul className="cv-compare-cell real"><li>—</li></ul>
          {targets.map((target) => (
            <ul key={target.id} className="cv-compare-cell">
              {[...target.baseline].sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status]).map((item) => <li key={item.key}><b className={`cv-mark ${item.status}`} title={STATUS_LABEL[item.status]}>{STATUS_MARK[item.status]}</b><span>{item.label}</span></li>)}
            </ul>
          ))}
        </div>
        {sections.map((name) => (
          <div key={name} className="cv-compare-row">
            <h4 className="cv-compare-section">{SECTION_LABEL[name]}</h4>
            <ul className="cv-compare-cell real">{(real[name] ?? []).map((text, index) => <li key={index}>{text}</li>)}</ul>
            {targets.map((target) => (
              <ul key={target.id} className="cv-compare-cell">
                {(target.sections[name] ?? []).map((item, index) => (
                  <li key={index}>{item.status && <b className={`cv-mark ${item.status}`} title={STATUS_LABEL[item.status]}>{STATUS_MARK[item.status]}</b>}<span>{item.text}</span></li>
                ))}
              </ul>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
