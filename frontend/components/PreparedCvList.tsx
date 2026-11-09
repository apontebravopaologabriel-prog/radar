"use client";
import { useCallback, useEffect, useState } from "react";
import { studioApi, type StudioPackage } from "../lib/cv-studio-api";
import { PREPARE_CV_EVENT } from "../lib/cv-events";
import { startProcess } from "../lib/processes-api";

export default function PreparedCvList({ jobId }: { jobId?: string }) {
  const [packages, setPackages] = useState<StudioPackage[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const result = await studioApi.packages();
      setPackages(result.packages);
      setError("");
    } catch {
      setError("No se pudieron cargar los archivos preparados.");
    }
  }, []);
  useEffect(() => {
    void load();
    window.addEventListener("radar:jobs-changed", load);
    return () => window.removeEventListener("radar:jobs-changed", load);
  }, [load]);
  const shown = packages.filter((item) => !jobId || item.job_id === jobId);
  if (jobId && !shown.length && !error) return null;

  if (jobId) {
    return (
      <details className="prepared-cvs">
        <summary>CVs preparados{shown.length ? ` · ${shown.length}` : ""}</summary>
        {error && <p role="alert">{error} <button type="button" onClick={() => void load()}>Reintentar</button></p>}
        {shown.map((pkg) => (
          <div key={pkg.job_id}>
            <p>{pkg.title} · {pkg.company}</p>
            <div className="process-actions">
              {pkg.files.filter((f) => f.exists !== false).map((f) => (
                <a key={f.name} href={studioApi.fileUrl(pkg.job_id, f.name)} download>{f.name}</a>
              ))}
              <button type="button" onClick={() => window.dispatchEvent(new CustomEvent(PREPARE_CV_EVENT, { detail: { jobId: pkg.job_id } }))}>Revisar CV</button>
            </div>
          </div>
        ))}
      </details>
    );
  }

  return (
    <section className="cv-desk-panel" aria-label="CVs preparados">
      <div className="cv-desk-panel-head">
        <h3>CVs listos para postular{shown.length ? ` · ${shown.length}` : ""}</h3>
        <p className="cv-note">Archivos PDF/Word generados en tu equipo. Súbelos al portal de la oferta o pásalos a Procesos si te contactan.</p>
      </div>
      {error && <p role="alert" className="cv-note">{error} <button type="button" className="mycv-link" onClick={() => void load()}>Reintentar</button></p>}
      {!shown.length && !error && (
        <p className="cv-desk-empty">Aún no has descargado ningún CV adaptado. Elige una oferta con ★ o busca una abajo para generar tu PDF.</p>
      )}
      {shown.length > 0 && (
        <ul className="cv-desk-list">
          {shown.map((pkg) => (
            <li key={pkg.job_id} className="cv-desk-card">
              <div className="cv-desk-card-main">
                <strong>{pkg.title}</strong>
                <span>{pkg.company || "Empresa no indicada"} · {pkg.status === "applied" ? `Postulada ${pkg.applied_at?.slice(0, 10) ?? ""}` : "CV preparado"}</span>
                <div className="cv-desk-files">
                  {pkg.files.filter((f) => f.exists !== false).map((f) => (
                    <a key={f.name} className="cv-file-pill" href={studioApi.fileUrl(pkg.job_id, f.name)} download>
                      ↓ {f.name}
                    </a>
                  ))}
                </div>
              </div>
              <div className="cv-desk-card-actions">
                <button type="button" className="mycv-button" onClick={() => window.dispatchEvent(new CustomEvent(PREPARE_CV_EVENT, { detail: { jobId: pkg.job_id } }))}>Abrir CV</button>
                <button type="button" className="mycv-button" onClick={() => startProcess({ id: pkg.job_id, title: pkg.title, company: pkg.company })}>Me contactaron</button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
