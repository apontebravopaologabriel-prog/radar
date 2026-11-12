import type { components, paths } from "./api-schema";
import { requestJson } from "./http";

export type AnalysisScope = components["schemas"]["AnalysisScope"];
export type Overview = components["schemas"]["Overview"];
export type Breakdown = components["schemas"]["Breakdown"];
type OffersOperation = paths["/api/analytics/offers"]["get"];
export type Dimension = NonNullable<OffersOperation["parameters"]["query"]>["dimension"];
export type AnalysisSelection = { dimension: NonNullable<Dimension>; value: string; label: string };
export type AnalysisOffers = OffersOperation["responses"][200]["content"]["application/json"];

export function scopeParams(scope: AnalysisScope): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(scope)) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  params.sort();
  return params;
}

export function fetchOverview(scopeQuery: string, signal?: AbortSignal) {
  return requestJson<Overview>(`/api/analytics/overview?${scopeQuery}`, { signal });
}

export function fetchAnalysisOffers(scopeQuery: string, selection: AnalysisSelection | null, offset: number, signal?: AbortSignal) {
  const params = new URLSearchParams(scopeQuery);
  if (selection) { params.set("dimension", selection.dimension); params.set("value", selection.value); }
  params.set("limit", "25"); params.set("offset", String(offset));
  return requestJson<AnalysisOffers>(`/api/analytics/offers?${params}`, { signal });
}
