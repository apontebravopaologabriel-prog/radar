"use client";

import { useEffect, useRef, useState } from "react";
import { fetchCvSelection, fetchCvTargets } from "../lib/cv-api";
import { fetchApplications } from "../lib/applications-api";
import type { CvBaselineItem, CvTarget } from "../lib/cv-types";
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

export default function CvInsights({ onOpenJob }: { onOpenJob?: (id: string) => void }) {
  const [items, setItems] = useState<{ id: string; title: string; company: string | null; source: "★" | "Postulé" }[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [targets, setTargets] = useState<CvTarget[]>([]);
  const [search, setSearch] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const pickerToggleRef = useRef<HTMLButtonElement>(null);
  const [targetsError, setTargetsError] = useState("");
  const [loadingTargets, setLoadingTargets] = useState(false);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [focused, setFocused] = useState<{ jobId: string; key: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchCvSelection(controller.signal), fetchApplications(controller.signal)])
      .then(([favorites, applications]) => {
        const seen = new Set<string>();
        const choices = [
          ...favorites.map((item) => ({ id: item.id, title: item.title, company: item.company, source: "★" as const })),
          ...applications.filter((item) => item.applied_at || ["applied", "responded", "interview", "offer"].includes(item.status)).map((item) => ({ id: item.job_id, title: item.title, company: item.company, source: "Postulé" as const })),
        ].filter((item) => { if (seen.has(item.id)) return false; seen.add(item.id); return true; });
        if (!controller.signal.aborted) {
          setItems(choices);
          setLoaded(true);
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "No se pudo comparar.");
      });
    return () => controller.abort();
  }, []);

  const idsKey = picked.join(",");
  useEffect(() => {
    setTargets([]);
    setTargetsError("");
    setLoadingTargets(Boolean(idsKey));
    if (!idsKey) return;
    const controller = new AbortController();
    fetchCvTargets(idsKey.split(","), controller.signal)
      .then((result) => { if (!controller.signal.aborted) setTargets(result.targets); })
      .catch((reason) => {
        if (!controller.signal.aborted) setTargetsError(String(reason));
      })
      .finally(() => { if (!controller.signal.aborted) setLoadingTargets(false); });
    return () => controller.abort();
  }, [idsKey]);

  const rows = Array.from(new Map(targets.flatMap((target) => target.baseline.map((item) => [item.key, item.label] as const))).entries());
  const selected = picked.flatMap((id) => items.filter((item) => item.id === id));
  const matches = items.filter((item) => !picked.includes(item.id) && `${item.title} ${item.company ?? ""}`.toLocaleLowerCase("es").includes(search.trim().toLocaleLowerCase("es")));
  useEffect(() => { if (pickerOpen) searchRef.current?.focus(); }, [pickerOpen]);

  function remove(id: string) {
    setPicked((current) => current.filter((candidate) => candidate !== id));
    setFocused(null);
  }

  function add(id: string) {
    setPicked((current) => current.length < 4 && !current.includes(id) ? [...current, id] : current);
    setFocused(null);
    setSearch("");
    setPickerOpen(false);
    requestAnimationFrame(() => pickerToggleRef.current?.focus());
  }
  const gaps = targets.flatMap((target) => target.baseline.filter((item) => item.status === "falta").map((item) => item.key));
  const topGaps = Array.from(new Map(gaps.map((key) => [key, { key, label: rows.find(([rowKey]) => rowKey === key)?.[1] ?? key, count: gaps.filter((value) => value === key).length }])).values()).sort((a, b) => b.count - a.count).slice(0, 5);
  const focusedTarget = targets.find((target) => target.id === focused?.jobId);
  const focusedItem = focusedTarget?.baseline.find((item) => item.key === focused?.key);

  return (
    <section className="cv-insights" aria-label="Matriz comparativa de ofertas guardadas">
      <header className="cv-insights-head">
        <h2>Comparar requisitos</h2>
        <span className="cv-legend">✓ Con evidencia · ~ Por revisar · — Sin evidencia · · No detectado</span>
      </header>
      {error && <p role="alert" className="cv-note">{error}</p>}
      {!loaded && !error && <p className="cv-note">Cargando…</p>}
      {loaded && items.length === 0 && <p className="cv-note">Guarda ofertas con ★ o registra una postulación para compararlas aquí.</p>}
      {items.length > 0 && (
        <>
          <div className="cv-compare-toolbar">
            <div className="cv-compare-chips">{selected.map((item) =>
              <button key={item.id} className="cv-compare-chip" type="button" title={item.title}
                aria-label={`Quitar ${item.title}`} onClick={() => remove(item.id)}>{item.title} <span aria-hidden="true">×</span></button>
            )}</div>
            <button ref={pickerToggleRef} type="button" aria-expanded={pickerOpen} aria-controls="cv-compare-picker"
              onClick={() => setPickerOpen((value) => !value)}>{pickerOpen ? "Cerrar selector" : "Agregar oferta"} · {picked.length}/4</button>
          </div>
          <div id="cv-compare-picker" className="cv-compare-picker" hidden={!pickerOpen} onKeyDown={(event) => {
            if (event.key === "Escape") { event.stopPropagation(); setPickerOpen(false); pickerToggleRef.current?.focus(); }
          }}>
            <input ref={searchRef} className="cv-compare-search" type="search" aria-label="Buscar oferta para comparar" placeholder="Buscar entre favoritos y postulaciones…" value={search} onChange={(event) => setSearch(event.target.value)} />
            <ul>{matches.slice(0, 12).map((item) => <li key={item.id}>
              <button type="button" disabled={picked.length >= 4} onClick={() => add(item.id)}><strong>{item.title}</strong><small>{item.company || "Empresa no indicada"} · {item.source}</small></button>
            </li>)}</ul>
            {matches.length === 0 && <p className="cv-note">No hay ofertas que coincidan.</p>}
            {matches.length > 12 && <p className="cv-note">Busca por puesto o empresa para ver otras ofertas.</p>}
            {picked.length >= 4 && <p className="cv-note">Quita una oferta para agregar otra.</p>}
          </div>
          {picked.length === 0 && <p className="cv-note">Agrega hasta cuatro ofertas para comparar sus requisitos.</p>}
          {targetsError && <p className="cv-note" role="alert">{targetsError}</p>}
          {loadingTargets && <p className="cv-note" role="status">Cargando requisitos…</p>}
          {!loadingTargets && targets.length > 0 && rows.length === 0 && <p className="cv-note">Sin requisitos estructurados detectados en estas ofertas.</p>}

          {targets.length > 0 && rows.length > 0 && <div className="cv-matrix">
            <table>
              <thead>
                <tr>
                  <th>Requisito</th>
                  {targets.map((target) => (
                    <th key={target.id}>
                      <button type="button" onClick={() => onOpenJob ? onOpenJob(target.id) : window.dispatchEvent(new CustomEvent(PREPARE_CV_EVENT, { detail: { jobId: target.id } }))}>
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
                        <td key={target.id} className={`cv-cell ${item ? item.status : "none"}`}>
                          <button type="button" aria-label={`${target.company || target.title}, ${label}: ${item ? LABEL[item.status] : "no detectado"}`} aria-pressed={focused?.jobId === target.id && focused.key === key} onClick={() => setFocused({ jobId: target.id, key })}>{item ? MARK[item.status] : "·"}</button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>}

          {focused && <div className="cv-matrix-detail" role="region" aria-label="Detalle del requisito">
            <button type="button" className="cv-matrix-close" aria-label="Cerrar detalle del requisito" onClick={() => setFocused(null)}>×</button>
            <strong>{focusedItem?.label || rows.find(([key]) => key === focused.key)?.[1] || "Requisito"} · {focusedTarget?.company || focusedTarget?.title}</strong>
            <p>{focusedItem ? `${LABEL[focusedItem.status]}. ${focusedItem.reason}` : "Este requisito no se detectó en esta oferta."}</p>
            {focusedItem?.quote && <blockquote>“{focusedItem.quote}”</blockquote>}
            {focusedTarget && <button type="button" onClick={() => onOpenJob ? onOpenJob(focusedTarget.id) : window.dispatchEvent(new CustomEvent(PREPARE_CV_EVENT, { detail: { jobId: focusedTarget.id } }))}>Abrir oferta ↗</button>}
          </div>}

          {targets.length > 0 && (
            <div className="cv-improve">
              <div className="cv-improve-head">
                <h3>Sin evidencia en la selección</h3>
                <button type="button" className="cv-pill-btn" onClick={() => window.dispatchEvent(new CustomEvent(MY_CV_EVENT))}>
                  + Añadir evidencia en Datos
                </button>
              </div>
              {topGaps.length ? (
                <ul className="cv-improve-list">
                  {topGaps.map((row) => (
                    <li key={row.key}>
                      <strong>{row.label}</strong>
                      <span>{row.count}/{targets.length} ofertas</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="cv-note">No se detectaron requisitos sin evidencia en estas ofertas.</p>
              )}
              <p className="cv-note">La ausencia de evidencia en tus datos no confirma que carezcas de una competencia.</p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
