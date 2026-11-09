import type { AnalyticsQueryResult, AnalyticsSchema, Filters, SkillOverview } from "../types";
import type { paths } from "./api-schema";
import { API_URL, requestJson } from "./http";

type JobPage = paths["/api/jobs"]["get"]["responses"][200]["content"]["application/json"];
type JobById = paths["/api/jobs/{job_id}"]["get"]["responses"][200]["content"]["application/json"];
type JobDescription = paths["/api/jobs/{job_id}/description"]["get"]["responses"][200]["content"]["application/json"];
type PersonalJobsPath = "/api/jobs/hidden" | "/api/jobs/favorites" | "/api/jobs/applied";
type PersonalJobs = paths[PersonalJobsPath]["get"]["responses"][200]["content"]["application/json"];

export async function fetchJobs(filters: Filters, signal?: AbortSignal): Promise<JobPage["jobs"]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  params.set("slim", "1"); // sin descripciones: pesan ~80 % del listado; se piden al abrir una oferta
  params.set("include_applied", "false");
  return (await requestJson<JobPage>(`/api/jobs?${params.toString()}`, { signal })).jobs;
}

export async function fetchJobDescription(id: string, signal?: AbortSignal): Promise<JobDescription["description"]> {
  return (await requestJson<JobDescription>(`/api/jobs/${encodeURIComponent(id)}/description`, { signal })).description;
}

async function fetchPersonalJobs(path: PersonalJobsPath, signal?: AbortSignal): Promise<PersonalJobs["jobs"]> {
  return (await requestJson<PersonalJobs>(path, { signal })).jobs;
}

export const fetchHiddenJobs = (signal?: AbortSignal) => fetchPersonalJobs("/api/jobs/hidden", signal);
export const fetchFavoriteJobs = (signal?: AbortSignal) => fetchPersonalJobs("/api/jobs/favorites", signal);
export const fetchAppliedJobs = (signal?: AbortSignal) => fetchPersonalJobs("/api/jobs/applied", signal);

export async function fetchJob(id: string, signal?: AbortSignal): Promise<JobById["job"] | null> {
  const response = await fetch(`${API_URL}/api/jobs/${encodeURIComponent(id)}`, { signal });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return ((await response.json()) as JobById).job;
}

export async function updateJobFavorite(id: string, favorite: boolean): Promise<void> {
  const response = await fetch(`${API_URL}/api/jobs/${id}/favorite`, { method: favorite ? "PUT" : "DELETE" });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
}

export async function fetchSkillOverview(filters: Pick<Filters, "area" | "seniority" | "work_mode" | "max_age_days" | "geo_scope" | "market_id" | "profile_mode" | "relevance_tier" | "min_salary" | "max_salary">, signal?: AbortSignal): Promise<SkillOverview> {
  const params = new URLSearchParams();
  params.set("include_applied", "false");
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  const response = await fetch(`${API_URL}/api/skills/overview?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return (await response.json()) as SkillOverview;
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

export type ImportedJobResult = {
  job_id: string;
  status: "created" | "updated";
  source: string;
  title: string;
  company: string | null;
  location: string | null;
  district: string | null;
  work_mode: string | null;
  seniority: string | null;
  primary_area: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  fit_score: number | null;
  is_favorite: boolean;
  application_status: string | null;
  url: string;
  radar_link: string;
};

export async function importJobUrl(body: {
  url: string;
  title?: string;
  company?: string;
  location?: string;
  description?: string;
  favorite?: boolean;
  application_status?: string;
  notes?: string;
}): Promise<ImportedJobResult> {
  const response = await fetch(`${API_URL}/api/jobs/import-url`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail || `La API respondió ${response.status}`);
  }
  return (await response.json()) as ImportedJobResult;
}
