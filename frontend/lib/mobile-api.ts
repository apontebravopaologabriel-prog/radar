const API_URL = process.env.NEXT_PUBLIC_RADAR_API_URL
  || (typeof window !== "undefined" && window.location.port !== "3000" ? window.location.origin : "http://127.0.0.1:8100");

export class AuthRequired extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (response.status === 401) throw new AuthRequired();
  if (!response.ok) {
    let detail = `La API respondió ${response.status}`;
    try { const body = await response.json(); if (typeof body.detail === "string") detail = body.detail; } catch { /* sin cuerpo */ }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export type TodayJob = {
  id: string; title: string; company: string | null; location: string | null; url: string | null;
  published_at: string | null; work_mode: string | null; score: number | null;
  strong_matches: string[]; missing_skills: string[]; why: string; is_favorite: boolean;
};
export type NearbyJob = { id: string; title: string; company: string | null; location: string | null; place: string;
  precision: "district" | "city" | "department"; km: number; url: string | null; published_at: string | null;
  work_mode: string | null; area: string | null; is_favorite: boolean };
export type Nearby = { origin: string; radius_km: number; total: number; jobs: NearbyJob[];
  by_place: { place: string; count: number }[]; precision: string };
export type MapPlace = { name: string; latitude: number; longitude: number; precision: "district" | "city" | "department"; count: number };
export type MapPlaces = { places: MapPlace[]; total: number; unlocated: number };
export type Today = { profile_configured: boolean; jobs: TodayJob[] };
export type SkillImpact = { profile_configured: boolean; threshold?: number; jobs_considered?: number;
  skills: { skill: string; jobs: number; avg_gain: number; crossing: number }[] };
export type Application = { id: string; job_id: string; title: string; company: string | null; status: string;
  notes: string | null; applied_at: string | null; updated_at: string; url: string | null };
export type Career = { active: string; name: string; areas: { core: string[]; adjacent: string[] };
  skills: { name: string; type: string; category: string | null }[]; queries: string[];
  weights: Record<string, number>; tracks: { id: string; name: string }[] };
export type AgentSettings = { provider: string; base_url: string; model: string; has_key: boolean; needs_key: boolean;
  ready: boolean; monthly_token_cap: number; tokens_used_this_month: number;
  providers: Record<string, { base_url: string; model: string }> };
export type ProfileInput = { name: string; education?: string; areas: string[]; locations: string[];
  work_modes: string[]; skills: Record<string, string> };

export const api = {
  authStatus: () => request<{ required: boolean; authenticated: boolean }>("/api/auth/status"),
  login: (token: string) => request<{ authenticated: boolean }>("/api/auth/login", { method: "POST", body: JSON.stringify({ token }) }),
  logout: () => request<{ authenticated: boolean }>("/api/auth/logout", { method: "POST" }),
  today: () => request<Today>("/api/today?limit=8"),
  setupStatus: () => request<{ complete: boolean; steps: { id: string; done: boolean; detail: string }[] }>("/api/setup/status"),
  places: () => request<{ groups: { label: string; places: string[] }[]; default: string | null }>("/api/places"),
  mapPlaces: () => request<MapPlaces>("/api/map/places"),
  nearby: (place: string, radiusKm: number) =>
    request<Nearby>(`/api/nearby?place=${encodeURIComponent(place)}&radius_km=${radiusKm}&limit=40`),
  impact: () => request<SkillImpact>("/api/skills/impact?limit=4"),
  applications: () => request<{ applications: Application[] }>("/api/applications"),
  setApplication: (jobId: string, status: string, notes?: string) =>
    request<{ status: string }>(`/api/applications/${jobId}`, { method: "PUT", body: JSON.stringify({ status, notes }) }),
  favorite: (jobId: string, on: boolean) =>
    request<{ is_favorite: boolean }>(`/api/jobs/${jobId}/favorite`, { method: on ? "PUT" : "DELETE" }),
  hide: (jobId: string) =>
    request<{ status: string }>(`/api/jobs/${jobId}/status`, { method: "PATCH", body: JSON.stringify({ status: "hidden", reason: "not_interested" }) }),
  career: () => request<Career>("/api/career"),
  setCareer: (careerId: string) => request<Career>("/api/career", { method: "PUT", body: JSON.stringify({ career_id: careerId }) }),
  setWeights: (weights: Record<string, number>) =>
    request<Career>("/api/career/weights", { method: "PUT", body: JSON.stringify({ weights }) }),
  saveProfile: (profile: ProfileInput) => request<{ profile_id: string }>("/api/profile", { method: "PUT", body: JSON.stringify(profile) }),
  agentSettings: () => request<AgentSettings>("/api/agent/settings"),
  saveAgentSettings: (body: { provider: string; model?: string; base_url?: string; api_key?: string; monthly_token_cap?: number }) =>
    request<AgentSettings>("/api/agent/settings", { method: "PUT", body: JSON.stringify(body) }),
  confirm: (body: { tool_call_id: string; name: string; arguments: Record<string, unknown>; approve: boolean }) =>
    request<{ message: ApiMessage; result: unknown }>("/api/chat/confirm", { method: "POST", body: JSON.stringify(body) }),
};

export type ApiMessage = { role: "user" | "assistant" | "tool"; content: string | null; tool_call_id?: string;
  tool_calls?: { id: string; type: "function"; function: { name: string; arguments: string } }[] };
export type PendingAction = { id: string; name: string; arguments: Record<string, unknown>; description: string };
export type ChatEvent =
  | { type: "text"; delta: string }
  | { type: "assistant_message"; message: ApiMessage }
  | { type: "tool_result"; message: ApiMessage; name: string }
  | { type: "pending"; actions: PendingAction[] }
  | { type: "error"; message: string }
  | { type: "done" };

/** Lee el SSE de /api/chat y entrega cada evento; termina cuando el servidor cierra el stream. */
export async function streamChat(messages: ApiMessage[], onEvent: (event: ChatEvent) => void, signal?: AbortSignal): Promise<void> {
  const response = await fetch(`${API_URL}/api/chat`, {
    method: "POST", credentials: "include", signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (response.status === 401) throw new AuthRequired();
  if (!response.ok || !response.body) throw new Error(`La API respondió ${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, cut).trim();
      buffer = buffer.slice(cut + 2);
      if (frame.startsWith("data:")) onEvent(JSON.parse(frame.slice(5)) as ChatEvent);
    }
  }
}

export const STATUS_LABELS: Record<string, string> = {
  saved: "Guardadas", applied: "Postulé", interview: "Entrevista", offer: "Oferta", rejected: "Descartadas",
};
export const STATUS_ORDER = ["saved", "applied", "interview", "offer", "rejected"];
