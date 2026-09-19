"use client";

import { useEffect, useState } from "react";
import { CV_PHOTO_URL, fetchCvProfile, fetchCvTargets } from "../lib/api";
import type { CvGap, CvItem, CvMatrix, CvProfile, CvStatus, CvTarget } from "../types";

const STATUS_MARK: Record<CvStatus, string> = { cubierto: "✓", parcial: "~", falta: "✗" };
const STATUS_LABEL: Record<CvStatus, string> = { cubierto: "Cubierto", parcial: "Parcial", falta: "Falta" };
const ORIGIN_LABEL: Record<CvItem["origin"], string> = { explicito: "explícito", inferido: "inferido", tipico: "típico" };
const KIND_LABEL: Record<CvGap["kind"], string> = { dias: "días", semanas: "semanas", no_cerrable_rapido: "no cierra rápido" };
const SECTION_LABEL: Record<string, string> = { summary: "Resumen", education: "Formación", experience: "Experiencia", tools: "Herramientas", certifications: "Certificaciones" };
const SECTION_ORDER = ["summary", "experience", "tools", "education", "certifications"];

export default function CvView() {
  const [profile, setProfile] = useState<CvProfile | null>(null);
  const [targets, setTargets] = useState<CvTarget[]>([]);
  const [matrix, setMatrix] = useState<CvMatrix | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);
  const [compareIds, setCompareIds] = useState<string[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchCvProfile(controller.signal), fetchCvTargets(controller.signal)])
      .then(([nextProfile, data]) => {
        setProfile(nextProfile);
        setTargets(data.targets);
        setMatrix(data.matrix);
        setLoaded(true);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "No se pudieron cargar los CVs");
        setLoaded(true);
      });
    return () => controller.abort();
  }, []);

  const open = comparing ? null : targets.find((target) => target.id === openId) ?? null;
  const compared = targets.filter((target) => compareIds.includes(target.id));

  function showMatrix() { setComparing(false); setOpenId(null); }
  function showTarget(id: string) { setComparing(false); setOpenId(id); }
  function showCompare() {
    setComparing(true);
    setOpenId(null);
    setCompareIds((current) => current.length ? current : targets.slice(0, 3).map((target) => target.id));
  }
  function toggleCompare(id: string) {
    setCompareIds((current) => current.includes(id) ? current.filter((value) => value !== id) : current.length >= 3 ? current : [...current, id]);
  }

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
          <button type="button" role="tab" aria-selected={!open && !comparing} className={!open && !comparing ? "active" : ""} onClick={showMatrix}>Matriz</button>
          {targets.length > 1 && <button type="button" role="tab" aria-selected={comparing} className={comparing ? "active" : ""} onClick={showCompare}>Comparar</button>}
          {targets.map((target) => <button key={target.id} type="button" role="tab" aria-selected={openId === target.id} className={openId === target.id ? "active" : ""} onClick={() => showTarget(target.id)} title={target.title}>{target.company}</button>)}
        </nav>
      </header>
      <div className="cv-body">
        {error && <p className="cv-note">{error}</p>}
        {loaded && !error && targets.length === 0 && <p className="cv-note">Sin CVs objetivo. Se esperan archivos en <code>targets/</code> junto a la base de datos.</p>}
        {!open && !comparing && matrix && matrix.rows.length > 0 && <MatrixTable matrix={matrix} onOpen={showTarget} />}
        {comparing && <CompareGrid profile={profile} targets={targets} selected={compared} onToggle={toggleCompare} />}
        {open && <TargetCv target={open} />}
      </div>
    </div>
  );
}

function MatrixTable({ matrix, onOpen }: { matrix: CvMatrix; onOpen: (id: string) => void }) {
  return (
    <section className="cv-matrix" aria-label="Matriz de brechas">
      <p className="cv-note">Ordenada por cuántos puestos dejan el requisito abierto. Clic en un puesto para ver su CV ideal.</p>
      <table>
        <thead>
          <tr>
            <th scope="col">Requisito</th>
            {matrix.columns.map((column) => <th key={column.id} scope="col"><button type="button" onClick={() => onOpen(column.id)} title={column.title}>{column.company}</button></th>)}
            <th scope="col">Abiertos</th>
          </tr>
        </thead>
        <tbody>
          {matrix.rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">{row.label}</th>
              {matrix.columns.map((column) => {
                const status = row.cells[column.id];
                return <td key={column.id} className={status ? `cv-cell ${status}` : "cv-cell none"} title={status ? STATUS_LABEL[status] : "No aplica"}>{status ? STATUS_MARK[status] : "·"}</td>;
              })}
              <td className="cv-open-count">{row.open_count}/{matrix.columns.length}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="cv-legend"><span>✓ cubierto</span><span>~ parcial</span><span>✗ falta</span><span>· no aplica</span></p>
    </section>
  );
}

function TargetCv({ target }: { target: CvTarget }) {
  return (
    <article className="cv-doc">
      <div className="cv-banner" role="note">HIPOTÉTICO — no enviar</div>
      <h3>{target.title}</h3>
      <p className="cv-doc-meta">{target.company}{target.location ? ` · ${target.location.job} · ${target.location.km_from_home} km desde ${target.location.home} (aprox.)` : ""}</p>
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
                {(item.quote || item.reason) && <em>{item.quote ? `“${item.quote}”` : item.reason}{item.quote && item.reason ? ` — ${item.reason}` : ""}</em>}
              </li>
            ))}
          </ul>
        </section>
      ))}
      {target.gaps?.length > 0 && (
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

function CompareGrid({ profile, targets, selected, onToggle }: { profile: CvProfile | null; targets: CvTarget[]; selected: CvTarget[]; onToggle: (id: string) => void }) {
  const real = realColumn(profile);
  const sections = SECTION_ORDER.filter((name) => (real[name]?.length ?? 0) > 0 || selected.some((target) => target.sections[name]?.length));
  const columns = `minmax(200px, 1fr) repeat(${selected.length}, minmax(200px, 1fr))`;
  return (
    <section className="cv-compare" aria-label="Comparar CVs objetivo">
      <p className="cv-note">Tu perfil real a la izquierda; hasta 3 puestos hipotéticos a la derecha. Cada sección queda alineada.</p>
      <div className="cv-compare-picker" role="group" aria-label="Puestos a comparar">
        {targets.map((target) => <button key={target.id} type="button" aria-pressed={selected.some((item) => item.id === target.id)} className={selected.some((item) => item.id === target.id) ? "active" : ""} onClick={() => onToggle(target.id)}>{target.company}</button>)}
      </div>
      <div className="cv-compare-grid" style={{ gridTemplateColumns: columns }}>
        <div className="cv-compare-head real">Tú (real)</div>
        {selected.map((target) => <div key={target.id} className="cv-compare-head"><span className="cv-banner-inline">HIPOTÉTICO</span>{target.company}<small>{target.title}</small></div>)}
        {sections.map((name) => (
          <div key={name} className="cv-compare-row">
            <h4 className="cv-compare-section">{SECTION_LABEL[name]}</h4>
            <ul className="cv-compare-cell real">{(real[name] ?? []).map((text, index) => <li key={index}>{text}</li>)}</ul>
            {selected.map((target) => (
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
