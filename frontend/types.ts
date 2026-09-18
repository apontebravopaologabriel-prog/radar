export type WorkMode = "onsite" | "hybrid" | "remote" | "unknown";

export type Job = {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  district: string | null;
  seniority: string | null;
  work_mode: WorkMode;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  url: string | null;
  published_at: string | null;
  description: string | null;
  primary_area: string | null;
  sector: string | null;
  relevance_tier: "core" | "adjacent" | "out_of_focus";
  relevance_score: number;
  relevance_evidence: string | null;
  hours_per_week: number | null;
  schedule_text: string | null;
  application_status: string;
  user_status?: "visible" | "hidden";
  user_reason?: string | null;
  is_favorite?: boolean;
  latitude: number | null;
  longitude: number | null;
  location_precision: "district" | "city" | "unknown";
  location_confidence: number;
};

export type Filters = {
  search: string;
  area: string;
  seniority: string;
  work_mode: string;
  min_salary: string;
  max_age_days: string;
  source?: string;
  skill?: string;
  relevance_tier?: string;
};

export type MapMode = "jobs" | "heatmap" | "radar" | "skills";

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

export type SkillSnapshot = { date: string; skill: string; value: number };

export type DistrictSummary = {
  key: string;
  district: string;
  count: number;
  latitude: number;
  longitude: number;
};
