export type CvStatus = "cubierto" | "parcial" | "falta";

export type CvBaselineItem = {
  key: string;
  label: string;
  requirement: "required" | "preferred" | "desirable" | "unknown";
  category: "skill" | "experience" | "education";
  blocker: boolean;
  status: CvStatus;
  reason: string;
  quote?: string | null;
  source: "codigo";
};

export type CvReadiness = {
  percent: number | null;
  covered: number;
  partial: number;
  missing: number;
  blockers: number;
  low_data: boolean;
};

export type CvItem = {
  text: string;
  origin: "explicito" | "inferido" | "tipico";
  key?: string;
  label?: string;
  status?: CvStatus;
  status_source?: "codigo" | "agente";
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

export type CvLocation = { job: string | null; home: string | null; km_from_home: number | null };

export type CvSelectionItem = {
  id: string;
  title: string;
  company: string | null;
  location: CvLocation;
  readiness: CvReadiness;
  has_enrichment: boolean;
};

export type CvTarget = CvSelectionItem & {
  job_id: string;
  aviso?: string | null;
  baseline: CvBaselineItem[];
  soft_skills: string[];
  sections: Record<string, CvItem[]>;
  gaps: CvGap[];
};

export type CvMatrix = {
  columns: { id: string; title: string; company: string | null }[];
  rows: { key: string; label: string; cells: Record<string, CvStatus>; agent_cells: string[]; open_count: number }[];
};

export type CvProfile = {
  name: string;
  headline: string;
  home_district: string;
  has_photo: boolean;
  summary?: string;
  education?: { institution: string; program: string; status: string }[];
  experience?: { role: string; company: string; from: string; to: string }[];
  certifications?: { name: string; issuer: string; date: string }[];
  tools_declared_in_db?: Record<string, string>;
};
