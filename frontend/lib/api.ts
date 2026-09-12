import type { Filters, Job } from "../types";

const API_URL = process.env.NEXT_PUBLIC_RADAR_API_URL || "http://127.0.0.1:8100";

export async function fetchJobs(filters: Filters, signal?: AbortSignal): Promise<Job[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  const response = await fetch(`${API_URL}/api/jobs?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  const payload = (await response.json()) as { jobs: Job[] };
  return payload.jobs;
}
