"use client";

import { useEffect, useState } from "react";
import { fetchJob, fetchJobDescription } from "../lib/api";
import { renderMarkdown } from "../lib/radar-format";
import JobFacts from "./radar/JobFacts";
import type { TrackedApplication } from "../lib/applications-api";
import "./applications.css";

type TrackingOffer = {
  job_id?: string | null;
  title: string;
  company?: string | null;
  url?: string | null;
} & Partial<Pick<TrackedApplication, "location" | "work_mode" | "salary_min" | "salary_max" | "salary_currency" | "published_at">>;

export default function TrackingOfferDetail({ item, children }: { item: TrackingOffer; children?: React.ReactNode }) {
  const [job, setJob] = useState<Awaited<ReturnType<typeof fetchJob>>>(null);
  const jobId = item.job_id;
  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    fetchJob(jobId, controller.signal)
      .then((found) => { if (!controller.signal.aborted) setJob(found); })
      .catch(() => { /* The tracking record still has the last saved offer data. */ });
    return () => controller.abort();
  }, [jobId]);

  const offer = job?.id === jobId ? job : null;
  const url = item.url || offer?.url;
  return <>
    <h3 className="tracking-offer-title">{url ? <a href={url} target="_blank" rel="noreferrer">{item.title} ↗</a> : item.title}</h3>
    <p>{item.company || offer?.company || "Empresa no indicada"}</p>
    {(jobId || url) && <JobFacts job={offer ?? {
      district: null,
      location: item.location ?? null,
      work_mode: item.work_mode ?? null,
      salary_min: item.salary_min ?? null,
      salary_max: item.salary_max ?? null,
      salary_currency: item.salary_currency ?? null,
      published_at: item.published_at ?? null,
      application_status: "unknown",
    }} />}
    {children}
    {jobId && <JobDescriptionBlock key={jobId} jobId={jobId} />}
  </>;
}

/** Offer text Radar saved locally; click it to expand or collapse, like the map card. */
function JobDescriptionBlock({ jobId }: { jobId: string }) {
  const [state, setState] = useState<{ jobId: string; text: string | null } | "error" | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetchJobDescription(jobId, controller.signal)
      .then((text) => setState({ jobId, text: text ?? null }))
      .catch(() => { if (!controller.signal.aborted) setState("error"); });
    return () => controller.abort();
  }, [jobId]);
  const current = state && state !== "error" && state.jobId === jobId ? state : null;
  if (state === "error") return <p className="job-description-note">No se pudo cargar la descripción.</p>;
  if (!current) return null;
  if (!current.text?.trim()) return <p className="job-description-note">Sin descripción guardada.</p>;
  return <div
    className={`job-description-body${open ? " is-open" : ""}`}
    role="button"
    tabIndex={0}
    aria-expanded={open}
    title={open ? "Clic para contraer" : "Clic para ver completa"}
    onClick={(event) => { if (!(event.target as Element).closest("a")) setOpen((value) => !value); }}
    onKeyDown={(event) => { if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); setOpen((value) => !value); } }}
  >{renderMarkdown(current.text)}</div>;
}
