import type { AnalyticsQueryResult, AnalyticsSchema, CvMatrix, CvProfile, CvTarget, Filters, Job, SkillOverview } from "../types";

const API_URL = process.env.NEXT_PUBLIC_RADAR_API_URL
  || (typeof window !== "undefined" && window.location.port !== "3000" ? window.location.origin : "http://127.0.0.1:8100");

export async function fetchJobs(filters: Filters, signal?: AbortSignal): Promise<Job[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  params.set("slim", "1"); // sin descripciones: pesan ~80 % del listado; se piden al abrir una oferta
  const response = await fetch(`${API_URL}/api/jobs?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  const payload = (await response.json()) as { jobs: Job[] };
  return payload.jobs;
}

export async function fetchJobDescription(id: string, signal?: AbortSignal): Promise<string | null> {
  const response = await fetch(`${API_URL}/api/jobs/${id}/description`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return ((await response.json()) as { description: string | null }).description;
}

export async function fetchHiddenJobs(signal?: AbortSignal): Promise<Job[]> {
  const response = await fetch(`${API_URL}/api/jobs/hidden`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  const payload = (await response.json()) as { jobs: Job[] };
  return payload.jobs;
}

export async function fetchFavoriteJobs(signal?: AbortSignal): Promise<Job[]> {
  const response = await fetch(`${API_URL}/api/jobs/favorites`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  const payload = (await response.json()) as { jobs: Job[] };
  return payload.jobs;
}

export async function fetchJob(id: string, signal?: AbortSignal): Promise<Job | null> {
  const response = await fetch(`${API_URL}/api/jobs/${encodeURIComponent(id)}`, { signal });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return ((await response.json()) as { job: Job }).job;
}

export async function fetchAppliedJobs(signal?: AbortSignal): Promise<Job[]> {
  const response = await fetch(`${API_URL}/api/jobs/applied`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return ((await response.json()) as { jobs: Job[] }).jobs;
}

export async function updateJobFavorite(id: string, favorite: boolean): Promise<void> {
  const response = await fetch(`${API_URL}/api/jobs/${id}/favorite`, { method: favorite ? "PUT" : "DELETE" });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
}

export async function fetchSkillOverview(filters: Pick<Filters, "area" | "seniority" | "work_mode" | "max_age_days">, signal?: AbortSignal): Promise<SkillOverview> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  const response = await fetch(`${API_URL}/api/skills/overview?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return (await response.json()) as SkillOverview;
}

export async function fetchJobsForSkill(skill: string, signal?: AbortSignal): Promise<Job[]> {
  const params = new URLSearchParams({ skill, max_age_days: "365" });
  const response = await fetch(`${API_URL}/api/jobs?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return ((await response.json()) as { jobs: Job[] }).jobs;
}

export async function updateJobStatus(id: string, status: "visible" | "hidden", reason?: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/jobs/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, reason }),
  });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
}

export async function runAnalyticsQuery(sql: string, signal?: AbortSignal): Promise<AnalyticsQueryResult> {
  const response = await fetch(`${API_URL}/api/analytics/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sql }),
    signal,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || `La API respondió ${response.status}`);
  }
  return (await response.json()) as AnalyticsQueryResult;
}

export async function fetchAnalyticsSchema(signal?: AbortSignal): Promise<AnalyticsSchema> {
  const response = await fetch(`${API_URL}/api/analytics/schema`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return (await response.json()) as AnalyticsSchema;
}

export const CV_PHOTO_URL = `${API_URL}/api/cv/photo`;

export async function fetchCvProfile(signal?: AbortSignal): Promise<CvProfile | null> {
  const response = await fetch(`${API_URL}/api/cv/profile`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return ((await response.json()) as { profile: CvProfile | null }).profile;
}

export async function fetchCvTargets(signal?: AbortSignal): Promise<{ targets: CvTarget[]; matrix: CvMatrix }> {
  const response = await fetch(`${API_URL}/api/cv/targets`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return (await response.json()) as { targets: CvTarget[]; matrix: CvMatrix };
}

export type TrackedApplication = { id: string; job_id: string; title: string; company: string | null; status: string; notes: string | null; applied_at: string | null; updated_at: string; url: string | null };

export async function fetchApplications(signal?: AbortSignal): Promise<TrackedApplication[]> {
  const response = await fetch(`${API_URL}/api/applications`, { signal, credentials: "include" });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return ((await response.json()) as { applications: TrackedApplication[] }).applications;
}

export async function updateApplication(jobId: string, status: string, notes?: string | null): Promise<void> {
  const response = await fetch(`${API_URL}/api/applications/${encodeURIComponent(jobId)}`, {
    method: "PUT", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status, notes: notes ?? null }),
  });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
}
