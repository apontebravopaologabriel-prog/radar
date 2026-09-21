import type { CvBuildPreview, CvBuildResult, CvMatrix, CvPlan, CvProfile, CvSelectionItem, CvTarget } from "./cv-types";

const API_URL = process.env.NEXT_PUBLIC_RADAR_API_URL
  || (typeof window !== "undefined" && window.location.port !== "3000" ? window.location.origin : "http://127.0.0.1:8100");

export const CV_PHOTO_URL = `${API_URL}/api/cv/photo`;

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { signal });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return (await response.json()) as T;
}

export async function fetchCvProfile(signal?: AbortSignal): Promise<CvProfile | null> {
  return (await getJson<{ profile: CvProfile | null }>("/api/cv/profile", signal)).profile;
}

export async function fetchCvSelection(signal?: AbortSignal): Promise<CvSelectionItem[]> {
  return (await getJson<{ targets: CvSelectionItem[] }>("/api/cv/selection", signal)).targets;
}

export async function fetchCvTargets(ids: string[], signal?: AbortSignal): Promise<{ targets: CvTarget[]; matrix: CvMatrix }> {
  const query = ids.length ? `?ids=${encodeURIComponent(ids.join(","))}` : "";
  return getJson<{ targets: CvTarget[]; matrix: CvMatrix }>(`/api/cv/targets${query}`, signal);
}

export async function fetchCvPlan(signal?: AbortSignal): Promise<CvPlan> {
  return getJson<CvPlan>("/api/cv/plan", signal);
}

export const cvFileUrl = (path: string) => `${API_URL}/api/cv/files/${path.split("/").map(encodeURIComponent).join("/")}`;

export async function fetchCvBuildPreview(jobId: string, signal?: AbortSignal): Promise<CvBuildPreview> {
  return getJson<CvBuildPreview>(`/api/cv/build/preview?job_id=${encodeURIComponent(jobId)}`, signal);
}

export async function buildCvFiles(jobId: string): Promise<CvBuildResult> {
  const response = await fetch(`${API_URL}/api/cv/build`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job_id: jobId }),
  });
  if (!response.ok) {
    const detail = await response.json().then((body: { detail?: string }) => body.detail).catch(() => undefined);
    throw new Error(detail ?? `La API respondió ${response.status}`);
  }
  return (await response.json()) as CvBuildResult;
}
