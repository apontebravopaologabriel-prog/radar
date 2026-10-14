const API_URL = process.env.NEXT_PUBLIC_RADAR_API_URL
  || (typeof window !== "undefined" && window.location.port !== "3000" ? window.location.origin : "http://127.0.0.1:8100");

export type StudioBullet = { id: string; text: string; trace?: string; edited?: string; matched?: string[] };
export type StudioEntry = { id: string; title: string; detail: string; bullets: StudioBullet[]; edited?: string };
export type StudioSimple = { id: string; title: string; detail: string; edited?: string };
export type StudioOmitted = { id: string; section: string; text: string; reason: string; owner: string | null };
export type StudioBox = { id: string; page: number; x: number; y: number; w: number; h: number };
export type StudioOp =
  | { op: "omit"; id: string }
  | { op: "include"; id: string }
  | { op: "move"; id: string; to: number }
  | { op: "edit"; id: string; text: string; field?: "text" | "title" | "detail" }
  | { op: "option"; name: "template" | "photo" | "pages"; value: unknown };
export type StudioFact = { kind: "number" | "name" | "skill"; value: string };
export type StudioSuggestion = { id: string; note: string; ops: StudioOp[]; flags: { op: number; id: string; facts: StudioFact[] }[]; safe: boolean };
export type StudioFile = { name: string; format: string; size: number; pages: number | null; exists?: boolean; modified_after_export?: boolean };
export type StudioPackage = { id: string; job_id: string; folder: string; folder_exists: boolean; files: StudioFile[]; status: "prepared" | "applied"; exported_at: string | null; applied_at: string | null; title: string; company: string };
export type StudioState = {
  job_id: string;
  selection: {
    job: { id: string; title: string; company: string | null; url?: string | null }; language: "es" | "en"; pages_budget: number;
    header: { name: string; headline: string; contact: string }; summary: string;
    experience: StudioEntry[]; projects: StudioEntry[]; certifications: StudioSimple[]; education: StudioSimple[];
    skills: string[]; languages: string[]; omitted: StudioOmitted[];
    coverage: { demonstrated: string[]; listed_only: string[]; missing: string[]; percent: number | null };
    edits: Record<string, { from: string | null; by: string }>;
  };
  stale_ops: StudioOp[];
  document: { template: string; photo: boolean; pages_budget: number; ops: number; can_undo: boolean; can_redo: boolean; updated_at: string };
  render: { pages: number; boxes: StudioBox[]; over_budget: boolean; page_mm: [number, number] };
  warnings: string[]; suggestions: StudioSuggestion[]; photo_available: boolean; templates: Record<string, string>;
};
export type StudioSettings = { export_dir: string; default_export_dir: string; filename_pattern: string; ascii_filenames: boolean; placeholders: string[]; example: string };

async function call<T>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init, signal, credentials: "include",
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!response.ok) {
    const detail = await response.json().then((body: { detail?: string }) => body.detail).catch(() => undefined);
    throw new Error(detail ?? `La API respondió ${response.status}`);
  }
  return (await response.json()) as T;
}
const post = <T,>(path: string, body?: unknown) => call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const studioApi = {
  state: (jobId: string, signal?: AbortSignal) => call<StudioState>(`/api/cv/studio/${encodeURIComponent(jobId)}`, undefined, signal),
  pageUrl: (jobId: string, page: number, version: string) => `${API_URL}/api/cv/studio/${encodeURIComponent(jobId)}/page/${page}.png?v=${encodeURIComponent(version)}`,
  ops: (jobId: string, ops: StudioOp[]) => post<StudioState>(`/api/cv/studio/${encodeURIComponent(jobId)}/ops`, { ops }),
  options: (jobId: string, options: { template?: string; photo?: boolean; pages?: number }) => post<StudioState>(`/api/cv/studio/${encodeURIComponent(jobId)}/options`, options),
  undo: (jobId: string) => post<StudioState>(`/api/cv/studio/${encodeURIComponent(jobId)}/undo`),
  redo: (jobId: string) => post<StudioState>(`/api/cv/studio/${encodeURIComponent(jobId)}/redo`),
  reset: (jobId: string) => post<StudioState>(`/api/cv/studio/${encodeURIComponent(jobId)}/reset`),
  accept: (jobId: string, id: string) => post<StudioState>(`/api/cv/studio/${encodeURIComponent(jobId)}/suggestions/${encodeURIComponent(id)}/accept`),
  reject: (jobId: string, id: string) => post<StudioState>(`/api/cv/studio/${encodeURIComponent(jobId)}/suggestions/${encodeURIComponent(id)}/reject`),
  acceptSafe: (jobId: string) => post<StudioState>(`/api/cv/studio/${encodeURIComponent(jobId)}/suggestions/accept-safe`),
  exportFiles: (jobId: string, formats: string[]) => post<{ folder: string; files: StudioFile[]; pages: number; warnings: string[]; over_budget: boolean; package: StudioPackage }>(`/api/cv/studio/${encodeURIComponent(jobId)}/export`, { formats }),
  packages: () => call<{ packages: StudioPackage[]; settings: StudioSettings }>("/api/cv/packages"),
  fileUrl: (jobId: string, name: string) => `${API_URL}/api/cv/packages/${encodeURIComponent(jobId)}/files/${encodeURIComponent(name)}`,
  openFolder: (jobId: string) => post<{ opened: string }>(`/api/cv/packages/${encodeURIComponent(jobId)}/open-folder`),
  markApplied: (jobId: string, notes?: string) => post<StudioPackage>(`/api/cv/packages/${encodeURIComponent(jobId)}/applied`, { notes }),
  settings: () => call<StudioSettings>("/api/cv/settings"),
  saveSettings: (body: { export_dir?: string; filename_pattern?: string; ascii_filenames?: boolean }) => call<StudioSettings>("/api/cv/settings", { method: "PUT", body: JSON.stringify(body) }),
};
