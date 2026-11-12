import type { AnalysisScope } from "./analysis-api";
import { INITIAL_FILTERS } from "./radar-format";
import type { Filters } from "../types";

export function analysisScope(filters: Filters, skill: string | null): AnalysisScope {
  const optional = (value?: string) => value || undefined;
  return {
    market_id: filters.market_id, geo_scope: filters.geo_scope === "lima_callao" ? "lima_callao" : undefined,
    profile_mode: filters.profile_mode === "saved" ? "saved" : "market", max_age_days: Number(filters.max_age_days),
    search: optional(filters.search), area: optional(filters.area), skill: skill || undefined,
    seniority: optional(filters.seniority), work_mode: optional(filters.work_mode), source: optional(filters.source),
    relevance_tier: filters.relevance_tier ?? "market",
    min_salary: filters.min_salary === "" ? undefined : Number(filters.min_salary),
    max_salary: filters.max_salary === "" ? undefined : Number(filters.max_salary),
  };
}

export function filtersFromScope(scope: AnalysisScope): Filters {
  return { ...INITIAL_FILTERS, market_id: scope.market_id || INITIAL_FILTERS.market_id,
    profile_mode: scope.profile_mode || "market", max_age_days: String(scope.max_age_days || 7),
    search: scope.search || "", area: scope.area || "", seniority: scope.seniority || "",
    work_mode: scope.work_mode || "", source: scope.source || "", relevance_tier: scope.relevance_tier ?? "",
    min_salary: scope.min_salary == null ? "" : String(scope.min_salary), max_salary: scope.max_salary == null ? "" : String(scope.max_salary) };
}
