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
  primary_area: string | null;
  sector: string | null;
  hours_per_week: number | null;
  schedule_text: string | null;
  application_status: string;
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
};

export type MapMode = "jobs" | "heatmap" | "radar";

export type DistrictSummary = {
  key: string;
  district: string;
  count: number;
  latitude: number;
  longitude: number;
};
