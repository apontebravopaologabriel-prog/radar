export type CvEntry = Record<string, string | string[]>;
export type SetupDraft = {
  career_id: string; name: string; contact: Record<string, string>;
  education: CvEntry[]; experience: CvEntry[]; detected_skills: string[];
  source_text: string; source_name: string; warnings?: string[];
};
const base = process.env.NEXT_PUBLIC_RADAR_API_URL || (typeof window !== "undefined" && window.location.port !== "3000" ? window.location.origin : "http://127.0.0.1:8100");
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}/api/me${path}`, { credentials: "include", ...init });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : "No se pudo completar la operación.");
  }
  return response.json();
}
const json = (method: string, draft: SetupDraft) => ({ method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(draft) });
export const setupApi = {
  state: () => request<{ completed: boolean; draft: SetupDraft | null }>("/setup"),
  save: (draft: SetupDraft) => request<SetupDraft>("/setup/draft", json("PUT", draft)),
  confirm: (draft: SetupDraft) => request<{ saved: boolean; warnings: string[] }>("/setup/confirm", json("POST", draft)),
  preview: (file: File, career: string) => {
    const data = new FormData(); data.set("file", file); data.set("career_id", career);
    return request<SetupDraft>("/cv/preview", {method: "POST", body: data});
  },
  updates: () => request<{ available: boolean; latest?: string; current: string; url: string }>("/updates"),
};
