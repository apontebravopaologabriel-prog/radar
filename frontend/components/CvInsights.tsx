"use client";

import { useEffect, useState } from "react";
import { fetchCvPlan, fetchCvSelection, fetchCvTargets } from "../lib/cv-api";
import type { CvBaselineItem, CvPlan, CvSelectionItem, CvTarget } from "../lib/cv-types";
import { MY_CV_EVENT, PREPARE_CV_EVENT } from "../lib/cv-events";
import "./cv.css";

const LABEL = { cubierto: "Con evidencia", parcial: "Por revisar", falta: "Sin evidencia" };
const MARK = { cubierto: "✓", parcial: "~", falta: "—" };

export function RequirementTable({ items }: { items: CvBaselineItem[] }) {
  return items.length ? (
    <table className="cv-baseline">
      <thead>
        <tr>
          <th>Requisito</th>
          <th>Estado</th>
          <th>Evidencia / Motivo</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.key}>
            <td>{item.label}{item.blocker && " · clave"}</td>
            <td>{MARK[item.status]} {LABEL[item.status]}</td>
            <td className="reason">{item.reason}{item.quote && <small>“{item.quote}”</small>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  ) : (
    <p className="cv-note">Sin requisitos estructurados detectados en el aviso.</p>
  );
}

export default function CvInsights() {
  const [items, setItems] = useState<CvSelectionItem[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [targets, setTargets] = useState<CvTarget[]>([]);
  const [plan, setPlan] = useState<CvPlan | null>(null);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchCvSelection(controller.signal), fetchCvPlan(controller.signal)])
      .then(([selection, nextPlan]) => {
        setItems(selection);
        setPicked(selection.slice(0, 4).map((item) => item.id));
        setPlan(nextPlan);
        setLoaded(true);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "No se pudo comparar.");
      });
    return () => controller.abort();
  }, []);

  const idsKey = picked.join(",");
  useEffect(() => {
    setTargets([]);
    if (!idsKey) return;
    const controller = new AbortController();
    fetchCvTargets(idsKey.split(","), controller.signal)
      .then((result) => setTargets(result.targets))
      .catch((reason) => {
        if (!controller.signal.aborted) setError(String(reason));
      });
    return () => controller.abort();
  }, [idsKey]);

  const rows = Array.from(new Map(targets.flatMap((target) => target.baseline.map((item) => [item.key, item.label] as const))).entries());

  return (
    <section className="cv-insights" aria-label="Matriz comparativa de ofertas guardadas">
      <header className="cv-insights-head">
        <h2>Matriz de requisitos (★)</h2>
        <span className="cv-legend">✓ Con evidencia · ~ Por revisar · — Sin evidencia · máx. 4</span>
      </header>
      {error && <p role="alert" className="cv-note">{error}</p>}
      {!loaded && !error && <p className="cv-note">Cargando…</p>}
      {loaded && items.length === 0 && <p className="cv-note">Marca ofertas con ★ en el mapa para comparar sus requisitos.</p>}
      {items.length > 0 && (
        <>
          <div className="cv-compare-chips">
            {items.map((item) => {
              const active = picked.includes(item.id);
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`cv-compare-chip ${active ? "active" : ""}`}
                  disabled={!active && picked.length >= 4}
                  onClick={() => setPicked((current) => active ? current.filter((id) => id !== item.id) : [...current, item.id])}
                >
                  {item.title} <small>{item.company}</small>
                </button>
              );
            })}
          </div>

          <div className="cv-matrix">
            <table>
              <thead>
                <tr>
                  <th>Requisito</th>
                  {targets.map((target) => (
                    <th key={target.id}>
                      <button type="button" onClick={() => window.dispatchEvent(new CustomEvent(PREPARE_CV_EVENT, { detail: { jobId: target.id } }))}>
                        {target.company || target.title}
                        <small>{target.title}</small>
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(([key, label]) => (
                  <tr key={key}>
                    <th>{label}</th>
                    {targets.map((target) => {
                      const item = target.baseline.find((candidate) => candidate.key === key);
                      return (
                        <td key={target.id} className={`cv-cell ${item ? item.status : "none"}`} title={item ? `${LABEL[item.status]}: ${item.reason}` : "No detectado"}>
                          {item ? MARK[item.status] : "·"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {plan && (
            <div className="cv-improve">
              <div className="cv-improve-head">
                <h3>Brechas frecuentes en tus ★</h3>
                <button type="button" className="cv-pill-btn" onClick={() => window.dispatchEvent(new CustomEvent(MY_CV_EVENT))}>
                  + Añadir evidencia en Datos
                </button>
              </div>
              {plan.plan.length ? (
                <ul className="cv-improve-list">
                  {plan.plan.slice(0, 5).map((row) => (
                    <li key={row.key}>
                      <strong>{row.skill}</strong>
                      <span>{row.unlocks}/{plan.targets} ★{row.market_share_pct !== null ? ` · ${row.market_share_pct}% del mercado` : ""}</span>
                      {row.proposal?.action && <small>{row.proposal.action}</small>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="cv-note">Sin brechas de herramientas pendientes.</p>
              )}
              {plan.structural.length > 0 && (
                <details className="cv-structural">
                  <summary>Requisitos estructurales ({plan.structural.length})</summary>
                  <ul>
                    {plan.structural.map((row) => (
                      <li key={row.key}><strong>{row.label}</strong> · <span>{row.reason}</span></li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
