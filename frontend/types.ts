import type { components } from "./lib/api-schema";

type FullJob = components["schemas"]["FullJob"];

// A map row can receive its description and distance after the list is loaded.
export type Job = Omit<FullJob, "description"> & Partial<Pick<FullJob, "description">> & { distance_km?: number };

export type Filters = {
  geo_scope?: string;
  market_id?: string;
  profile_mode?: string;
  search: string;
  area: string;
  seniority: string;
  work_mode: string;
  min_salary: string;
  max_salary: string;
  max_age_days: string;
  source?: string;
  skill?: string;
  relevance_tier?: string;
};

export type MapMode = "jobs" | "heatmap" | "radar" | "analysis" | "cvs" | "applications";

export type SkillDemand = {
  name: string;
  category: string;
  skill_type: "technical" | "soft" | "language" | "methodology" | "domain";
  job_count: number;
  required_count: number;
  confidence: number;
  user_level: "none" | "basic" | "intermediate" | "advanced";
  interest: "low" | "medium" | "high" | null;
  evidence: string | null;
  share: number;
};

export type SkillOverview = {
  total_jobs: number;
  max_age_days: number;
  skills: SkillDemand[];
};

export type DistrictSummary = {
  key: string;
  district: string;
  count: number;
  latitude: number;
  longitude: number;
};

export type AnalyticsQueryResult = {
  columns: string[];
  rows: (string | number | null)[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
};

export type AnalyticsSchema = {
  tables: { table: string; columns: { name: string; type: string }[] }[];
};
