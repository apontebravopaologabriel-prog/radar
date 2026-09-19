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
  distance_km?: number;
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

export type MapMode = "jobs" | "heatmap" | "radar" | "analysis" | "cvs";

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

export type CvStatus = "cubierto" | "parcial" | "falta";

export type CvItem = {
  text: string;
  origin: "explicito" | "inferido" | "tipico";
  key?: string;
  status?: CvStatus;
  quote?: string;
  reason?: string;
};

export type CvGap = {
  item: string;
  kind: "dias" | "semanas" | "no_cerrable_rapido";
  action: string;
  estimate_days?: number;
  evidence_to_produce?: string;
};

export type CvTarget = {
  id: string;
  job_id: string;
  title: string;
  company: string;
  aviso?: string;
  location?: { job: string; km_from_home: number; home: string; method: string };
  sections: Record<string, CvItem[]>;
  gaps: CvGap[];
};

export type CvMatrix = {
  columns: { id: string; title: string; company: string }[];
  rows: { key: string; label: string; cells: Record<string, CvStatus>; open_count: number }[];
};

export type CvProfile = {
  name: string;
  headline: string;
  home_district: string;
  has_photo: boolean;
  summary?: string;
  education: { institution: string; program: string; status: string }[];
  experience?: { role: string; company: string; from: string; to: string }[];
  certifications?: { name: string; issuer: string; date: string }[];
  tools_declared_in_db?: Record<string, string>;
};
