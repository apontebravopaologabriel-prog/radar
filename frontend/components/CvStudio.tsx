"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { studioApi, type StudioCandidate, type StudioOp, type StudioPackage, type StudioSettings, type StudioState, type StudioSuggestion } from "../lib/cv-studio-api";
import "./cv-studio.css";

export type StudioContext = { jobId: string; title: string; company: string | null; selectedLine: { id: string; text: string } | null; pendingSuggestions: number };

type Line = { id: string; kind: string; text: string; trace?: string; editable: boolean; field: "text" | "title" | "detail"; edited?: string };

/** Todas las líneas del documento por id, para describir cambios y editar la seleccionada. */
function indexLines(state: StudioState): Map<string, Line> {
  const lines = new Map<string, Line>();
  const { selection } = state;
  lines.set("name", { id: "name", kind: "Nombre", text: selection.header.name, editable: false, field: "text" });
  lines.set("headline", { id: "headline", kind: "Titular", text: selection.header.headline, editable: true, field: "text" });
  lines.set("summary", { id: "summary", kind: "Perfil", text: selection.summary, editable: true, field: "text" });
  for (const [kind, entries] of [["Cargo", selection.experience], ["Proyecto", selection.projects]] as const) {
    for (const entry of entries) {
      lines.set(entry.id, { id: entry.id, kind, text: entry.title, editable: true, field: "title", edited: entry.edited });
      for (const bullet of entry.bullets) lines.set(bullet.id, { id: bullet.id, kind: "Viñeta", text: bullet.text, trace: bullet.trace, editable: true, field: "text", edited: bullet.edited });
    }
  }
  for (const [kind, entries] of [["Certificado", selection.certifications], ["Formación", selection.education]] as const) {
    for (const entry of entries) lines.set(entry.id, { id: entry.id, kind, text: entry.title, editable: true, field: "title", edited: entry.edited });
  }
  for (const item of selection.omitted) if (!lines.has(item.id)) lines.set(item.id, { id: item.id, kind: "Omitida", text: item.text, editable: false, field: "text" });
  return lines;
}

const clip = (text: string, size = 70) => (text.length > size ? `${text.slice(0, size - 1)}…` : text);

function describeOp(op: StudioOp, lines: Map<string, Line>): string {
  if (op.op === "option") return `Cambiar ${op.name === "template" ? "plantilla" : op.name === "photo" ? "foto" : "páginas"} a ${String(op.value)}`;
  const target = clip(lines.get(op.id)?.text ?? op.id);
  if (op.op === "omit") return `Quitar «${target}»`;
  if (op.op === "include") return `Volver a incluir «${target}»`;
  if (op.op === "move") return `Mover «${target}» a la posición ${op.to + 1}`;
  return `Reformular «${target}» → «${clip(op.text, 140)}»`;
}

function factLabel(kind: string, value: string): string {
  return `${kind === "number" ? "número" : kind === "skill" ? "herramienta" : "nombre"} «${value}»`;
}

export default function CvStudio({ jobId, onContext, advanced = false, onToggleAdvanced, onEditProfile }: { jobId: string; onContext?: (context: StudioContext | null) => void; advanced?: boolean; onToggleAdvanced?: () => void; onEditProfile?: () => void }) {
  const [state, setState] = useState<StudioState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [pkg, setPkg] = useState<StudioPackage | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [settings, setSettings] = useState<StudioSettings | null>(null);
  const [settingsDraft, setSettingsDraft] = useState({ export_dir: "", filename_pattern: "", ascii_filenames: true });
  const [showOmitted, setShowOmitted] = useState(false);
  const alive = useRef(true);

  const lines = useMemo(() => (state ? indexLines(state) : new Map<string, Line>()), [state]);
  const selected = selectedId ? lines.get(selectedId) ?? null : null;

  const refreshPackage = useCallback(async () => {
    const { packages, settings: current } = await studioApi.packages();
    if (!alive.current) return;
    setPkg(packages.find((item) => item.job_id === jobId) ?? null);
    setSettings(current);
    setSettingsDraft({ export_dir: current.export_dir, filename_pattern: current.filename_pattern, ascii_filenames: current.ascii_filenames });
  }, [jobId]);

  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    setState(null); setSelectedId(null); setNotice(null); setError(null);
    studioApi.state(jobId, controller.signal).then(setState).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "No se pudo abrir el Estudio"); });
    void refreshPackage().catch(() => undefined);
    return () => { alive.current = false; controller.abort(); };
  }, [jobId, refreshPackage]);

  // El agente puede dejar sugerencias mientras miras la página: se actualiza la lista cada pocos segundos.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible" || busy) return;
      studioApi.state(jobId).then((next) => { if (alive.current) setState((current) => (current && current.revision === next.revision && current.document.updated_at === next.document.updated_at && current.suggestions.length === next.suggestions.length ? current : next)); }).catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [jobId, busy]);

  useEffect(() => { setDraft(selected?.text ?? ""); }, [selected?.id, selected?.text]);

  useEffect(() => {
    if (!state || !onContext) return;
    onContext({ jobId, title: state.selection.job.title, company: state.selection.job.company, selectedLine: selected ? { id: selected.id, text: clip(selected.text, 200) } : null, pendingSuggestions: state.suggestions.length });
  }, [jobId, onContext, selected, state]);
  useEffect(() => () => onContext?.(null), [onContext]);
  useEffect(() => {
    if (!advanced) return;
    window.dispatchEvent(new CustomEvent("radar:agent-layout", { detail: { studio: true } }));
    return () => { window.dispatchEvent(new CustomEvent("radar:agent-layout", { detail: { studio: false } })); };
  }, [advanced]);

  async function run(action: () => Promise<StudioState>, success?: string) {
    setBusy(true); setError(null);
    try { const next = await action(); if (alive.current) { setState(next); setNotice(success ?? null); } }
    catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : "No se pudo completar la acción"); }
    finally { if (alive.current) setBusy(false); }
  }
  const apply = (ops: StudioOp[], success?: string) => run(() => studioApi.ops(jobId, ops), success);

  async function exportFiles(formats: string[]) {
    setBusy(true); setError(null); setNotice(null);
    try {
      const result = await studioApi.exportFiles(jobId, formats, state?.revision);
      if (!alive.current) return;
      setPkg(result.package);
      setNotice(`Exportado: ${result.files.map((file) => file.name).join(", ")}${result.over_budget ? " (excede páginas)" : ""}`);
      const file = result.files.find((item) => item.format === "pdf") ?? result.files[0];
      if (file) {
        const link = document.createElement("a"); link.href = studioApi.fileUrl(jobId, file.name); link.download = file.name; link.click();
      }
      window.dispatchEvent(new CustomEvent("radar:jobs-changed"));
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : "No se pudo exportar"); }
    finally { if (alive.current) setBusy(false); }
  }

  async function simple<T>(action: () => Promise<T>, success: string, after?: (value: T) => void) {
    setError(null);
    try { const value = await action(); after?.(value); setNotice(success); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo completar la acción"); }
  }

  if (error && !state) return <p className="cv-note cv-problem" role="alert">{error}</p>;
  if (!state) return <p className="cv-note">Generando vista previa…</p>;

  const { selection, document: doc, render } = state;
  const version = `${state.revision}-${doc.updated_at}-${doc.ops}-${doc.template}-${doc.photo}-${doc.pages_budget}`;
  const sidebar = doc.template === "sidebar";

  const reorder = (container: { id: string }[], index: number, delta: number) => {
    const to = index + delta;
    if (to >= 0 && to < container.length) void apply([{ op: "move", id: container[index].id, to }]);
  };
  const row = (id: string, text: string, container: { id: string }[], index: number, extra?: string) => (
    <li key={id} className={`cvs-row ${selectedId === id ? "selected" : ""}`}>
      <input type="checkbox" checked onChange={() => void apply([{ op: "omit", id }])} aria-label={`Incluir: ${text}`} title="Quitar de este CV" />
      <button type="button" className="cvs-text" onClick={() => setSelectedId(id)}>{clip(text, 90)}{lines.get(id)?.edited && <em className="cvs-tag">{lines.get(id)?.edited === "agent" ? "IA" : "edit"}</em>}{extra && <small>{extra}</small>}</button>
      <span className="cvs-move">
        <button type="button" onClick={() => reorder(container, index, -1)} disabled={index === 0} aria-label="Subir">↑</button>
        <button type="button" onClick={() => reorder(container, index, 1)} disabled={index === container.length - 1} aria-label="Bajar">↓</button>
      </span>
    </li>
  );

  return (
    <section className={`cvs ${advanced ? "" : "cvs-simple"}`} aria-label="Vista previa y edición del CV">
      {advanced && <aside className="cvs-side">
        <h4>Estructura del documento</h4>
        <ul className="cvs-list">
          <li className={`cvs-row ${selectedId === "headline" ? "selected" : ""}`}><span className="cvs-label">Titular</span><button type="button" className="cvs-text" onClick={() => setSelectedId("headline")}>{clip(selection.header.headline || "—", 90)}</button></li>
          <li className={`cvs-row ${selectedId === "summary" ? "selected" : ""}`}><span className="cvs-label">Perfil</span><button type="button" className="cvs-text" onClick={() => setSelectedId("summary")}>{clip(selection.summary || "—", 90)}</button></li>
        </ul>
        {selection.experience.length > 0 && <h4>Experiencia</h4>}
        <ul className="cvs-list">
          {selection.experience.map((role, roleIndex) => (
            <li key={role.id}>
              <ul className="cvs-list"><li className="cvs-role">{row(role.id, role.title, selection.experience, roleIndex, role.detail)}</li>
                {role.bullets.map((bullet, index) => row(bullet.id, bullet.text, role.bullets, index))}</ul>
            </li>
          ))}
        </ul>
        {selection.projects.length > 0 && <h4>Proyectos</h4>}
        <ul className="cvs-list">
          {selection.projects.map((project, projectIndex) => (
            <li key={project.id}><ul className="cvs-list"><li className="cvs-role">{row(project.id, project.title, selection.projects, projectIndex, project.detail)}</li>
              {project.bullets.map((bullet, index) => row(bullet.id, bullet.text, project.bullets, index))}</ul></li>
          ))}
        </ul>
        {selection.certifications.length > 0 && <h4>Certificaciones</h4>}
        <ul className="cvs-list">{selection.certifications.map((item, index) => row(item.id, item.title, selection.certifications, index, item.detail))}</ul>
        {selection.education.length > 0 && <h4>Formación</h4>}
        <ul className="cvs-list">{selection.education.map((item, index) => row(item.id, item.title, selection.education, index, item.detail))}</ul>

        {selection.omitted.length > 0 && (
          <>
            <button type="button" className="cvs-toggle" onClick={() => setShowOmitted(!showOmitted)} aria-expanded={showOmitted}>{showOmitted ? "▾" : "▸"} Omitidas ({selection.omitted.length})</button>
            {showOmitted && <ul className="cvs-list">{selection.omitted.map((item) => (
              <li key={item.id} className="cvs-row omitted">
                <button type="button" className="cvs-text" onClick={() => setSelectedId(item.id)}>{clip(item.text, 90)}<small>{item.reason}</small></button>
                <button type="button" onClick={() => void apply([{ op: "include", id: item.id }])} disabled={busy}>+</button>
              </li>
            ))}</ul>}
          </>
        )}

        <div className="cvs-side-foot">
          <button type="button" onClick={onEditProfile}>+ Añadir datos a mi trayectoria</button>
        </div>
      </aside>}

      <div className="cvs-main">
        <div className="cvs-toolbar" role="toolbar" aria-label="Opciones del CV">
          <button type="button" className={advanced ? "active" : ""} onClick={onToggleAdvanced} disabled={busy}>
            {advanced ? "▾ Esquema" : "▸ Esquema"}
          </button>
          <label>
            <select aria-label="Plantilla" value={doc.template} onChange={(event) => void run(() => studioApi.options(jobId, { template: event.target.value }))} disabled={busy}>
              {Object.entries(state.templates).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label>
            <select aria-label="Páginas" value={doc.pages_budget} onChange={(event) => void run(() => studioApi.options(jobId, { pages: Number(event.target.value) }))} disabled={busy}>
              {[1, 2, 3].map((n) => <option key={n} value={n}>{n} {n === 1 ? "pág." : "págs."}</option>)}
            </select>
          </label>
          {sidebar && (
            <label className={!state.photo_available ? "off" : ""} title={!state.photo_available ? "Sube tu foto en Ajustes → Mi CV" : ""}>
              <input type="checkbox" checked={doc.photo} disabled={busy || !state.photo_available} onChange={(event) => void run(() => studioApi.options(jobId, { photo: event.target.checked }))} /> Foto
            </label>
          )}
          {(doc.can_undo || doc.can_redo || doc.ops > 0) && (
            <>
              <button type="button" onClick={() => void run(() => studioApi.undo(jobId))} disabled={busy || !doc.can_undo} title="Deshacer">↶</button>
              <button type="button" onClick={() => void run(() => studioApi.redo(jobId))} disabled={busy || !doc.can_redo} title="Rehacer">↷</button>
              <button type="button" onClick={() => void run(() => studioApi.reset(jobId), "Reiniciado")} disabled={busy || (doc.ops === 0 && doc.template === "ats" && !doc.photo)} title="Reiniciar cambios">Reiniciar</button>
            </>
          )}
          <span className="cvs-spacer" />
          <button type="button" onClick={() => void exportFiles(["pdf", "docx"])} disabled={busy} title="Descargar PDF y Word">Word</button>
          <button type="button" className="primary" onClick={() => void exportFiles(["pdf"])} disabled={busy}>↓ Descargar PDF</button>
        </div>

        {state.suggestions.length > 0 && (
          <div className="cvs-suggestions" role="region" aria-label="Sugerencias del agente">
            <div className="cvs-suggestions-head"><b>Sugerencias del agente ({state.suggestions.length})</b>
              {state.suggestions.some((item) => item.safe) && <button type="button" onClick={() => void run(() => studioApi.acceptSafe(jobId), "Sugerencias aplicadas")} disabled={busy}>Aceptar seguras</button>}
            </div>
            {state.suggestions.map((item: StudioSuggestion) => (
              <article key={item.id} className={`cvs-suggestion ${item.safe ? "" : "unsafe"}`}>
                {item.note && <p className="cvs-note">{item.note}</p>}
                <ul>{item.ops.map((op, index) => <li key={index}>{describeOp(op, lines)}</li>)}</ul>
                {item.flags.map((flag) => <p key={`${flag.op}-${flag.id}`} className="cvs-flag">⚠ Dato no verificado: {flag.facts.map((fact) => factLabel(fact.kind, fact.value)).join(", ")}</p>)}
                <div className="cvs-actions">
                  <button type="button" disabled={busy || !item.safe} onClick={() => void run(() => studioApi.accept(jobId, item.id), "Cambio aceptado")}>Aceptar</button>
                  <button type="button" disabled={busy} onClick={() => void run(() => studioApi.reject(jobId, item.id))}>Rechazar</button>
                </div>
              </article>
            ))}
          </div>
        )}

        {(state.warnings.length > 0 || error || notice || state.stale_ops.length > 0) && (
          <div className="cvs-messages" role="status">
            {error && <p className="cvs-flag" role="alert">{error} <button type="button" disabled={busy} onClick={() => void run(() => studioApi.state(jobId))}>Reintentar</button></p>}
            {notice && <p className="cvs-ok">{notice}</p>}
            {state.stale_ops.length > 0 && <p className="cvs-flag">{state.stale_ops.length} edición anterior ya no aplica porque cambió tu trayectoria.</p>}
            {state.warnings.map((warning) => <p key={warning} className="cvs-flag">⚠ {warning}</p>)}
          </div>
        )}

        {selected && (
          <div className="cvs-editor">
            <div className="cvs-editor-head">
              <b>{selected.kind}</b>
              {selected.trace && <small>{selected.trace}</small>}
              <button type="button" onClick={() => setSelectedId(null)} aria-label="Cerrar edición">×</button>
            </div>
            {selected.id === "name" && <p className="cvs-note">El nombre se edita en Ajustes → Mi CV.</p>}
            {selected.editable ? (
              <>
                <textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={Math.min(5, Math.max(2, Math.ceil(draft.length / 75)))} maxLength={700} aria-label="Texto de la línea" />
                <div className="cvs-actions">
                  <button type="button" className="primary" disabled={busy || !draft.trim() || draft.trim() === selected.text} onClick={() => void apply([{ op: "edit", id: selected.id, text: draft.trim(), field: selected.field }], "Guardado en este CV")}>Guardar</button>
                  <button type="button" disabled={busy || lines.get(selected.id)?.kind === "Omitida"} onClick={() => { void apply([{ op: "omit", id: selected.id }]); setSelectedId(null); }}>Omitir línea</button>
                </div>
                {state.selection.edits[selected.id] && <p className="cvs-note">Original: «{clip(state.selection.edits[selected.id].from ?? "", 180)}»</p>}
              </>
            ) : selected.kind === "Omitida" ? <p className="cvs-note">Omitida. Usa «+» en Esquema para incluirla.</p> : null}
          </div>
        )}

        <div className="cvs-pages">
          {Array.from({ length: render.pages }, (_, index) => index + 1).map((page) => (
            <div key={page} className="cvs-page" style={{ aspectRatio: `${render.page_mm[0]} / ${render.page_mm[1]}` }}>
              {/* eslint-disable-next-line @next/next/no-img-element -- imagen dinámica del PDF del estudio */}
              <img src={studioApi.pageUrl(jobId, page, version)} alt={`Página ${page} del CV`} draggable={false} />
              {render.boxes.filter((box) => box.page === page).map((box, index) => (
                <button key={`${box.id}-${index}`} type="button" className={`cvs-hit ${selectedId === box.id ? "selected" : ""}`}
                  style={{ left: `${(box.x / render.page_mm[0]) * 100}%`, top: `${(box.y / render.page_mm[1]) * 100}%`, width: `${(box.w / render.page_mm[0]) * 100}%`, height: `${(box.h / render.page_mm[1]) * 100}%` }}
                  onClick={() => setSelectedId((current) => current === box.id ? null : box.id)}
                  title="Clic para editar u omitir esta línea"
                  aria-label={`Seleccionar: ${clip(lines.get(box.id)?.text ?? box.id, 50)}`} />
              ))}
              <span className="cvs-page-number">{page} / {render.pages}</span>
            </div>
          ))}
        </div>

        <footer className="cvs-foot">
          {pkg && (
            <div className="cvs-pkg-bar">
              <span>Archivos generados:</span>
              {pkg.files.map((file) => (
                <a key={file.name} className="cvs-file-chip" href={studioApi.fileUrl(jobId, file.name)} download={file.name}>
                  ↓ {file.name}
                </a>
              ))}
              <button type="button" onClick={() => void simple(() => studioApi.openFolder(jobId), "Carpeta abierta")}>Abrir carpeta</button>
              <button type="button" onClick={() => void simple(() => navigator.clipboard.writeText(pkg.folder), "Ruta copiada")}>Copiar ruta</button>
              {selection.job.url && <a className="cvs-button" href={selection.job.url} target="_blank" rel="noopener noreferrer">Portal ↗</a>}
            </div>
          )}
          <details className="cvs-settings">
            <summary>Ruta y formato de exportación</summary>
            {settings && (
              <div>
                <label>Carpeta<input value={settingsDraft.export_dir} onChange={(event) => setSettingsDraft({ ...settingsDraft, export_dir: event.target.value })} /></label>
                <label>Patrón ({settings.placeholders.map((p) => `{${p}}`).join(" ")})<input value={settingsDraft.filename_pattern} maxLength={80} onChange={(event) => setSettingsDraft({ ...settingsDraft, filename_pattern: event.target.value })} /></label>
                <label className="inline"><input type="checkbox" checked={settingsDraft.ascii_filenames} onChange={(event) => setSettingsDraft({ ...settingsDraft, ascii_filenames: event.target.checked })} /> Sin tildes</label>
                <button type="button" onClick={() => void simple(() => studioApi.saveSettings(settingsDraft), "Guardado", (value) => { setSettings(value); setSettingsDraft({ export_dir: value.export_dir, filename_pattern: value.filename_pattern, ascii_filenames: value.ascii_filenames }); })}>Guardar</button>
              </div>
            )}
          </details>
        </footer>
      </div>
    </section>
  );
}

/** Buscador compacto por si se usa de forma independiente. */
export function CvStudioPicker({ onOpen }: { onOpen: (jobId: string) => void }) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<StudioCandidate[] | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      studioApi.candidates(query, controller.signal).then(setItems).catch(() => undefined);
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);
  return (
    <section className="cvs-picker" aria-label="Elegir una oferta">
      <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar puesto o empresa…" aria-label="Buscar oferta" />
      <ul className="cvs-picker-list">
        {(items ?? []).map((job) => (
          <li key={job.id}>
            <button type="button" className="cvs-picker-row" onClick={() => onOpen(job.id)}>
              <strong>{job.title}</strong>
              <small>{job.company ?? "Empresa no indicada"}{job.location ? ` · ${job.location}` : ""}{job.is_favorite ? " · ★" : ""}</small>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
