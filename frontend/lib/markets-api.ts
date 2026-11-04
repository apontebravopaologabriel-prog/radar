export type Market = { id: string; name: string; areas: { core: string[]; adjacent: string[] } };
export type SearchPreferences = Partial<Record<"areas" | "roles" | "locations" | "work_modes" | "seniority" | "excluded_titles", string[]>>;
export type SearchProfile = { market_id: string; preferences: SearchPreferences; version: number };
export type MarketRefresh = { running: boolean; total: number; done: number; created: number; current: string | null; errors: string[]; market_ids?: string[] };
const BASE = process.env.NEXT_PUBLIC_RADAR_API_URL
  || (typeof window !== "undefined" && window.location.port !== "3000" ? window.location.origin : "http://127.0.0.1:8100");

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}/api${path}`, { credentials: "include", ...init });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `La API respondió ${response.status}`);
  }
  return response.json() as Promise<T>;
}
export const fetchMarkets = (signal?: AbortSignal) => request<{ markets: Market[] }>("/markets", { signal });
export const fetchSearchProfile = (market: string, signal?: AbortSignal) => request<SearchProfile>(`/markets/${encodeURIComponent(market)}/profile`, { signal });
export const saveSearchProfile = (market: string, preferences: SearchPreferences) => request<SearchProfile>(`/markets/${encodeURIComponent(market)}/profile`, {
  method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(preferences),
});
export const startMarketRefresh = (markets: string[]) => request<MarketRefresh>("/refresh", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ market_ids: markets, limit: 15 }),
});
export const fetchMarketRefresh = (signal?: AbortSignal) => request<MarketRefresh>("/refresh/status", { signal });
