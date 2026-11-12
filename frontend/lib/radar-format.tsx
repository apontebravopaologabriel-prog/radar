import { ReactNode } from "react";
import type { Filters, Job } from "../types";

export const INITIAL_FILTERS: Filters = {
  geo_scope: "lima_callao",
  market_id: "industrial_engineering",
  profile_mode: "market",
  search: "",
  area: "",
  seniority: "",
  work_mode: "",
  min_salary: "",
  max_salary: "",
  max_age_days: "7",
  source: "",
  relevance_tier: "market",
};

export const RADAR_RADII = [2, 5, 10] as const;
export type RadarView = "map" | "analysis" | "cvs" | "applications";
export type AnalysisFilterColumn = "area" | "skill" | "seniority" | "work_mode" | "district";

export const SENIORITY_VALUES: Record<string, string> = {
  practicante: "intern",
  intern: "intern",
  junior: "junior",
  intermedio: "mid",
  mid: "mid",
  senior: "senior",
};

export const WORK_MODE_VALUES: Record<string, string> = {
  presencial: "onsite",
  onsite: "onsite",
  híbrido: "hybrid",
  hibrido: "hybrid",
  hybrid: "hybrid",
  remoto: "remote",
  remote: "remote",
};

export const REASON_LABELS: Record<string, string> = {
  closed: "cerrada",
  not_interested: "sin interés",
  applied: "postulada",
  duplicate: "duplicada",
  other: "otro",
};

export const ARCHIVE_FILTERS: Array<[string, string]> = [
  ["", "todas"],
  ["closed", "cerradas"],
  ["not_interested", "sin interés"],
  ["applied", "postuladas"],
  ["duplicate", "duplicadas"],
  ["other", "otro"],
];

export function formatDate(value: string | null) {
  if (!value) return "Fecha no indicada";
  return new Intl.DateTimeFormat("es-PE", { day: "2-digit", month: "short" }).format(new Date(value));
}

export function formatSalary(job: Pick<Job, "salary_min" | "salary_max" | "salary_currency">) {
  if (job.salary_min === null && job.salary_max === null) return "No indicado";
  const currency = job.salary_currency === "PEN" ? "S/" : job.salary_currency || "";
  if (job.salary_min !== null && job.salary_max !== null) {
    return `${currency} ${job.salary_min.toLocaleString("es-PE")} – ${job.salary_max.toLocaleString("es-PE")}`;
  }
  return `${currency} ${(job.salary_min ?? job.salary_max)?.toLocaleString("es-PE")}`;
}

const INLINE_MARKDOWN = /(\*\*(.+?)\*\*|__(.+?)__|\*(.+?)\*|_(.+?)_|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))/g;

export function renderInlineMarkdown(value: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let key = 0;
  for (const match of value.matchAll(INLINE_MARKDOWN)) {
    const token = match[0];
    const index = match.index ?? cursor;
    if (index > cursor) nodes.push(value.slice(cursor, index));
    if (match[2] || match[3]) nodes.push(<strong key={`strong-${key++}`}>{match[2] || match[3]}</strong>);
    else if (match[4] || match[5]) nodes.push(<em key={`em-${key++}`}>{match[4] || match[5]}</em>);
    else if (match[6]) nodes.push(<code key={`code-${key++}`}>{match[6]}</code>);
    else if (match[7] && match[8]) nodes.push(<a key={`link-${key++}`} href={match[8]} target="_blank" rel="noreferrer">{match[7]}</a>);
    else nodes.push(token);
    cursor = index + token.length;
  }
  if (cursor < value.length) nodes.push(value.slice(cursor));
  return nodes;
}

export function renderMarkdown(value: string): ReactNode[] {
  const blocks: ReactNode[] = [];
  const lines = value.replace(/\r\n?/g, "\n").split("\n");
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let listOrdered: boolean | null = null;
  let key = 0;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(<p key={`paragraph-${key++}`}>{renderInlineMarkdown(paragraph.join(" "))}</p>);
    paragraph = [];
  };
  const flushList = () => {
    if (!listItems.length || listOrdered === null) return;
    const ListTag = listOrdered ? "ol" : "ul";
    blocks.push(<ListTag key={`list-${key++}`}>{listItems.map((item, index) => <li key={`item-${index}`}>{renderInlineMarkdown(item)}</li>)}</ListTag>);
    listItems = [];
    listOrdered = null;
  };

  for (const line of lines) {
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push(<h4 key={`heading-${key++}`}>{renderInlineMarkdown(heading[1])}</h4>);
      continue;
    }
    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const isOrdered = Boolean(ordered);
      if (listOrdered !== null && listOrdered !== isOrdered) flushList();
      listOrdered = isOrdered;
      listItems.push((ordered || unordered)?.[1] || "");
      continue;
    }
    flushList();
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  return blocks;
}

export function sourceLabel(url: string | null) {
  if (!url) return "Abrir oferta original";
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (host.includes("linkedin")) return "Ver en Linkedin";
    if (host.includes("indeed")) return "Ver en Indeed";
    if (host.includes("computrabajo")) return "Ver en Computrabajo";
    if (host.includes("bumeran")) return "Ver en Bumeran";
    if (host.includes("laborum")) return "Ver en Laborum";
    if (host.includes("empleosperu") || host.includes("gob.pe")) return "Ver en Empleos Perú";
    if (host.includes("glassdoor")) return "Ver en Glassdoor";
    if (host.includes("google")) return "Ver en Google Jobs";
  } catch {
    return "Abrir oferta original";
  }
  return "Ver oferta original";
}

export function sourceName(url: string | null) {
  if (!url) return "Fuente n/i";
  try {
    const host = new URL(url).hostname.toLowerCase().replace(/^www\./, "");
    if (host.includes("linkedin")) return "Linkedin";
    if (host.includes("indeed")) return "Indeed";
    if (host.includes("computrabajo")) return "Computrabajo";
    if (host.includes("bumeran")) return "Bumeran";
    if (host.includes("laborum")) return "Laborum";
    if (host.includes("empleosperu") || host.includes("gob.pe")) return "Empleos Perú";
    if (host.includes("glassdoor")) return "Glassdoor";
    if (host.includes("google")) return "Google";
    return host.split(".")[0] || "Fuente";
  } catch {
    return "Fuente n/i";
  }
}

export function portalKey(url: string | null) {
  if (!url) return "other";
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (host.includes("linkedin")) return "linkedin";
    if (host.includes("indeed")) return "indeed";
    if (host.includes("computrabajo")) return "computrabajo";
    if (host.includes("bumeran")) return "bumeran";
    if (host.includes("laborum")) return "laborum";
    if (host.includes("empleosperu") || host.includes("gob.pe")) return "empleos";
    if (host.includes("glassdoor")) return "glassdoor";
    if (host.includes("google")) return "google";
    return host.replace(/^www\./, "").split(".")[0] || "other";
  } catch {
    return "other";
  }
}

export function companyMapsUrl(job: Pick<Job, "company" | "district" | "location">) {
  if (!job.company?.trim()) return null;
  const query = [job.company.trim(), job.district || job.location || "Lima", "Perú"]
    .filter(Boolean)
    .join(", ");
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

export function distanceKm(from: { latitude: number; longitude: number }, to: { latitude: number; longitude: number }) {
  const earthRadiusKm = 6371;
  const latDelta = ((to.latitude - from.latitude) * Math.PI) / 180;
  const lonDelta = ((to.longitude - from.longitude) * Math.PI) / 180;
  const latitudeA = (from.latitude * Math.PI) / 180;
  const latitudeB = (to.latitude * Math.PI) / 180;
  const a = Math.sin(latDelta / 2) ** 2 + Math.cos(latitudeA) * Math.cos(latitudeB) * Math.sin(lonDelta / 2) ** 2;
  return 2 * earthRadiusKm * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
