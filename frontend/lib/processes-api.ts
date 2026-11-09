import type { paths } from "./api-schema";
import { requestJson } from "./http";

type Route = paths["/api/processes"];
export type ProcessInput = Route["post"]["requestBody"]["content"]["application/json"];
export type ProcessItem = Route["post"]["responses"][201]["content"]["application/json"];
export const PROCESS_EVENT = "radar:start-process";
export const STAGES = { contact: "Contacto", assessment: "Prueba", interview: "Entrevista", offer: "Oferta", closed: "Cerrado" } as const;
export async function fetchProcesses(signal?: AbortSignal) {
  return (await requestJson<Route["get"]["responses"][200]["content"]["application/json"]>("/api/processes", { signal })).processes;
}
export function saveProcess(value: ProcessInput, id?: string) {
  return requestJson<ProcessItem>(`/api/processes${id ? `/${encodeURIComponent(id)}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(value) });
}
export function startProcess(job: { id: string; company?: string | null; title: string; url?: string | null }) {
  window.dispatchEvent(new CustomEvent(PROCESS_EVENT, { detail: { job_id: job.id, company: job.company ?? "", title: job.title, url: job.url ?? "", stage: "contact" } }));
}
