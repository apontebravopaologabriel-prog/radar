import type { CvMatrix, CvSelectionItem, CvTarget } from "./cv-types";

const API_URL = process.env.NEXT_PUBLIC_RADAR_API_URL
  || (typeof window !== "undefined" && window.location.port !== "3000" ? window.location.origin : "http://127.0.0.1:8100");

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { signal, credentials: "include" });
  if (!response.ok) throw new Error(`La API respondió ${response.status}`);
  return (await response.json()) as T;
}

export async function fetchCvSelection(signal?: AbortSignal): Promise<CvSelectionItem[]> {
  return (await getJson<{ targets: CvSelectionItem[] }>("/api/cv/selection", signal)).targets;
}

export async function fetchCvTargets(ids: string[], signal?: AbortSignal): Promise<{ targets: CvTarget[]; matrix: CvMatrix }> {
  const query = ids.length ? `?ids=${encodeURIComponent(ids.join(","))}` : "";
  return getJson<{ targets: CvTarget[]; matrix: CvMatrix }>(`/api/cv/targets${query}`, signal);
}
