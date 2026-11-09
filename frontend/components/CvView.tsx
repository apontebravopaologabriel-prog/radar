"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Career } from "../lib/mobile-api";
import { cvProfileApi } from "../lib/cv-profile-api";
import { studioApi, type StudioCandidate, type StudioPackage } from "../lib/cv-studio-api";
import { fetchCvSelection, fetchCvTargets } from "../lib/cv-api";
import { MY_CV_EVENT, PREPARE_CV_EVENT } from "../lib/cv-events";
import type { CvSelectionItem, CvTarget } from "../lib/cv-types";
import CvHistoryEditor from "./CvHistoryEditor";
import CvStudio, { type StudioContext } from "./CvStudio";
import CvInsights, { RequirementTable } from "./CvInsights";
import MyCvProfile from "./MyCvProfile";
import "./cv.css";

type CvMode = "prepare" | "compare" | "profile";

export default function CvView({ onStudioContext, openJobId, onOpenJobConsumed }: { onStudioContext?: (context: StudioContext | null) => void; openJobId?: string | null; onOpenJobConsumed?: () => void }) {
  const [career, setCareer] = useState<Career | null>(null);
  const [mode, setMode] = useState<CvMode>("prepare");
  const [jobId, setJobId] = useState<string | null>(openJobId ?? null);
  const [advanced, setAdvanced] = useState(false);
  const [reqOpen, setReqOpen] = useState(false);
  const [target, setTarget] = useState<CvTarget | null>(null);
  const [starred, setStarred] = useState<CvSelectionItem[]>([]);
  const [packages, setPackages] = useState<StudioPackage[]>([]);
  const [search, setSearch] = useState("");
  const [candidates, setCandidates] = useState<StudioCandidate[] | null>(null);
  const [hasProfile, setHasProfile] = useState(true);
  const [profileName, setProfileName] = useState<string>("");
  const [originalName, setOriginalName] = useState<string | null>(null);
  const [revision, setRevision] = useState("");
  const [error, setError] = useState("");
  const [usingOriginal, setUsingOriginal] = useState(false);
  const [packageEpoch, setPackageEpoch] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const [next, me, selection, pkgs] = await Promise.all([
        cvProfileApi.read(),
        api.me(),
        fetchCvSelection().catch(() => [] as CvSelectionItem[]),
        studioApi.packages().then((r) => r.packages).catch(() => [] as StudioPackage[]),
      ]);
      setRevision(next.revision);
      setOriginalName(next.original_name ?? null);
      setHasProfile(Boolean(me.name));
      setProfileName(me.name || "");
      setStarred(selection);
      setPackages(pkgs);
      setJobId((current) => current ?? selection[0]?.id ?? pkgs[0]?.job_id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar tu CV.");
    }
  }, []);

  useEffect(() => {
    api.career().then(setCareer).catch((reason) => setError(String(reason)));
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!openJobId) return;
    setJobId(openJobId);
    setMode("prepare");
    setAdvanced(false);
    setReqOpen(false);
    setTarget(null);
    onOpenJobConsumed?.();
  }, [openJobId, onOpenJobConsumed]);

  useEffect(() => {
    const onPrepare = (event: Event) => {
      const id = (event as CustomEvent<{ jobId?: string }>).detail?.jobId;
      if (typeof id === "string" && id) {
        setJobId(id);
        setTarget(null);
        setAdvanced(false);
        setReqOpen(false);
        setMode("prepare");
      }
    };
    const onMyCv = () => setMode("profile");
    const onJobsChanged = () => {
      void fetchCvSelection().then(setStarred).catch(() => undefined);
      void studioApi.packages().then((r) => setPackages(r.packages)).catch(() => undefined);
    };
    window.addEventListener(PREPARE_CV_EVENT, onPrepare);
    window.addEventListener(MY_CV_EVENT, onMyCv);
    window.addEventListener("radar:jobs-changed", onJobsChanged);
    return () => {
      window.removeEventListener(PREPARE_CV_EVENT, onPrepare);
      window.removeEventListener(MY_CV_EVENT, onMyCv);
      window.removeEventListener("radar:jobs-changed", onJobsChanged);
    };
  }, []);

  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    fetchCvTargets([jobId], controller.signal)
      .then((result) => setTarget(result.targets[0] ?? null))
      .catch(() => undefined);
    return () => controller.abort();
  }, [jobId, revision]);

  useEffect(() => {
    const q = search.trim();
    if (!q) {
      setCandidates(null);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      studioApi.candidates(q, controller.signal).then(setCandidates).catch(() => undefined);
    }, 220);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [search]);

  const packageMap = useMemo(() => new Map(packages.map((p) => [p.job_id, p])), [packages]);

  const sourceItems = useMemo(() => {
    const seen = new Set<string>();
    const list: { id: string; title: string; company: string; badge: string; meta: string; hasPdf: boolean }[] = [];
    for (const item of starred) {
      seen.add(item.id);
      const hasPdf = packageMap.has(item.id);
      const meta = item.readiness.low_data
        ? (item.location?.job || "")
        : `✓${item.readiness.covered} ~${item.readiness.partial}${item.readiness.missing ? ` —${item.readiness.missing}` : ""}`;
      list.push({
        id: item.id,
        title: item.title,
        company: item.company || "Empresa no indicada",
        badge: hasPdf ? "PDF" : "★",
        meta,
        hasPdf,
      });
    }
    for (const pkg of packages) {
      if (seen.has(pkg.job_id)) continue;
      seen.add(pkg.job_id);
      list.push({
        id: pkg.job_id,
        title: pkg.title,
        company: pkg.company || "Empresa no indicada",
        badge: "PDF",
        meta: pkg.status === "applied" ? "postulada" : "preparado",
        hasPdf: true,
      });
    }
    return list;
  }, [starred, packages, packageMap]);

  function selectOffer(id: string) {
    setJobId(id);
    setTarget(null);
    setReqOpen(false);
    setMode("prepare");
  }

  async function restoreOriginalDocument() {
    if (!jobId || usingOriginal) return;
    setUsingOriginal(true);
    setError("");
    try {
      const result = await studioApi.useOriginal(jobId);
      const file = result.files[0];
      const link = document.createElement("a");
      link.href = studioApi.fileUrl(jobId, file.name);
      link.download = file.name;
      link.click();
      setPackageEpoch((value) => value + 1);
      window.dispatchEvent(new CustomEvent("radar:jobs-changed"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo usar el archivo original.");
    } finally {
      setUsingOriginal(false);
    }
  }

  const coveredCount = target ? target.baseline.filter((i) => i.status === "cubierto").length : 0;
  const totalReqCount = target ? target.baseline.length : 0;

  return (
    <div className="cv-view">
      <aside className="cv-rail" aria-label="Fuentes y modos de CV">
        <nav className="cv-rail-modes" aria-label="Modo">
          <button type="button" className={mode === "prepare" ? "active" : ""} onClick={() => setMode("prepare")}>
            CV
          </button>
          <button type="button" className={mode === "compare" ? "active" : ""} onClick={() => setMode("compare")}>
            Matriz{starred.length ? ` · ${starred.length}` : ""}
          </button>
          <button type="button" className={mode === "profile" ? "active" : ""} onClick={() => setMode("profile")}>
            Datos
          </button>
        </nav>

        <div className="cv-rail-search">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="⌕ Buscar en ★ o mercado…"
            aria-label="Buscar oferta"
          />
        </div>

        <div className="cv-rail-list" role="list">
          {search.trim() ? (
            candidates === null ? (
              <p className="cv-rail-empty">Buscando…</p>
            ) : candidates.length === 0 ? (
              <p className="cv-rail-empty">Sin coincidencias.</p>
            ) : (
              candidates.map((job) => (
                <button
                  key={job.id}
                  type="button"
                  role="listitem"
                  className={`cv-source-row ${mode === "prepare" && jobId === job.id ? "active" : ""}`}
                  onClick={() => selectOffer(job.id)}
                >
                  <div className="cv-source-top">
                    <span className="cv-source-title">{job.title}</span>
                    {packageMap.has(job.id) ? <em className="cv-source-badge pdf">PDF</em> : job.is_favorite ? <em className="cv-source-badge">★</em> : null}
                  </div>
                  <div className="cv-source-sub">
                    <span>{job.company ?? "Empresa"}</span>
                    {job.location && <small>{job.location}</small>}
                  </div>
                </button>
              ))
            )
          ) : sourceItems.length === 0 ? (
            <p className="cv-rail-empty">Guarda ofertas con ★ en el mapa o escribe arriba para buscar cualquier oferta.</p>
          ) : (
            sourceItems.map((item) => (
              <button
                key={item.id}
                type="button"
                role="listitem"
                className={`cv-source-row ${mode === "prepare" && jobId === item.id ? "active" : ""}`}
                onClick={() => selectOffer(item.id)}
              >
                <div className="cv-source-top">
                  <span className="cv-source-title">{item.title}</span>
                  <em className={`cv-source-badge ${item.hasPdf ? "pdf" : ""}`}>{item.badge}</em>
                </div>
                <div className="cv-source-sub">
                  <span>{item.company}</span>
                  {item.meta && <small>{item.meta}</small>}
                </div>
              </button>
            ))
          )}
        </div>

        <footer className="cv-rail-foot">
          <span>{profileName || "Sin perfil"}</span>
          <a href="/ajustes">Ajustes ↗</a>
        </footer>
      </aside>

      <div className="cv-stage">
        {error && <p role="alert" className="cv-note cv-stage-error">{error}</p>}

        {mode === "prepare" && (
          !hasProfile ? (
            <div className="cv-empty">
              <h3>Configura tu CV base</h3>
              <p>Importa tu archivo en Ajustes o añade tus datos para generar CVs por oferta.</p>
              <div className="mycv-actions">
                <a className="mycv-button primary" href="/ajustes">Importar en Ajustes</a>
                <button type="button" className="mycv-button" onClick={() => setMode("profile")}>Editar datos</button>
              </div>
            </div>
          ) : jobId ? (
            <div className="cv-workspace">
              <header className="cv-stage-bar">
                <div className="cv-stage-title">
                  <strong>{target?.title ?? "Cargando oferta…"}</strong>
                  {target?.company && <span>{target.company}{target.location?.job ? ` · ${target.location.job}` : ""}</span>}
                </div>
                <div className="cv-stage-actions">
                  {target && totalReqCount > 0 && (
                    <button
                      type="button"
                      className={`cv-pill-btn ${reqOpen ? "active" : ""}`}
                      onClick={() => setReqOpen((v) => !v)}
                    >
                      ✓ {coveredCount}/{totalReqCount} requisitos {reqOpen ? "▴" : "▾"}
                    </button>
                  )}
                  {originalName && (
                    <button
                      type="button"
                      className="cv-pill-btn"
                      disabled={usingOriginal}
                      onClick={() => void restoreOriginalDocument()}
                      title={`Asociar mi archivo original (${originalName})`}
                    >
                      {usingOriginal ? "Copiando…" : "Usar original"}
                    </button>
                  )}
                </div>
              </header>

              {reqOpen && target && (
                <div className="cv-req-drawer">
                  <RequirementTable items={target.baseline} />
                </div>
              )}

              <CvStudio
                key={`${jobId}-${revision}-${packageEpoch}`}
                jobId={jobId}
                onContext={onStudioContext}
                advanced={advanced}
                onToggleAdvanced={() => setAdvanced((value) => !value)}
                onEditProfile={() => setMode("profile")}
              />
            </div>
          ) : (
            <div className="cv-empty">
              <h3>Selecciona una oferta a la izquierda</h3>
              <p>Elige una de tus ★ o busca cualquier puesto en la columna izquierda para previsualizar y descargar tu CV en vivo.</p>
            </div>
          )
        )}

        {mode === "compare" && (
          <div className="cv-stage-pad">
            <CvInsights />
          </div>
        )}

        {mode === "profile" && (
          <div className="cv-stage-pad">
            {!hasProfile ? (
              career ? <MyCvProfile career={career} onChanged={() => void refresh()} /> : <p className="cv-note">Cargando…</p>
            ) : (
              <div className="mycv-profile">
                <CvHistoryEditor key={`history-${revision}`} onChanged={() => void refresh()} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
