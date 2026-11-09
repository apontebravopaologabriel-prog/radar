export const API_URL = process.env.NEXT_PUBLIC_RADAR_API_URL
  || (typeof window !== "undefined" && window.location.port !== "3000" ? window.location.origin : "http://127.0.0.1:8100");

export class AuthRequired extends Error {}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (typeof init?.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_URL}${path}`, { credentials: "include", ...init, headers });
  if (response.status === 401) throw new AuthRequired("La API respondió 401");
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `La API respondió ${response.status}`);
  }
  return response.json() as Promise<T>;
}
