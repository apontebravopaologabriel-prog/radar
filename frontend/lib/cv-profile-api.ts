import { API_URL, requestJson } from "./http";
import type { CvEntry } from "./setup-api";

export const ORIGINAL_CV_URL = `${API_URL}/api/me/cv/original`;
export const CV_SECTIONS = {
  experience: { label: "Experiencia", fields: { role: "Cargo *", company: "Empresa *", from: "Inicio (AAAA-MM)", to: "Fin (AAAA-MM o actual)", location: "Lugar", bullets: "Funciones y logros · uno por línea" } },
  education: { label: "Estudios", fields: { program: "Carrera o programa *", institution: "Institución *", status: "Estado o grado", from: "Inicio (AAAA-MM)", to: "Fin (AAAA-MM o actual)", skills: "Herramientas utilizadas · una por línea" } },
  certifications: { label: "Cursos y certificados", fields: { name: "Nombre *", issuer: "Institución", date: "Fecha (AAAA-MM)" } },
  projects: { label: "Proyectos", fields: { name: "Nombre *", description: "Qué hiciste", skills: "Herramientas utilizadas · una por línea", date: "Fecha (AAAA-MM)", link: "Enlace" } },
  languages: { label: "Idiomas", fields: { name: "Idioma *", level: "Nivel declarado", evidence: "Cómo lo demuestras (opcional)" } },
} as const;
export type CvSection = keyof typeof CV_SECTIONS;
export type CvSections = Record<CvSection, CvEntry[]>;
export type CvSnapshot = { sections: CvSections; revision: string; original_name?: string | null };
export type CvSaved = CvSnapshot & { undo: Partial<CvSections>; warnings: string[] };
export const cvProfileApi = {
  read: () => requestJson<CvSnapshot>("/api/me/cv"),
  save: (sections: Partial<CvSections>, revision: string) => requestJson<CvSaved>("/api/me/cv", { method: "PATCH", body: JSON.stringify({ sections, revision }) }),
};
export function entryLabel(entry: CvEntry): string {
  return [entry.role || entry.program || entry.name, entry.company || entry.institution || entry.issuer].filter(Boolean).join(" · ") || "Nuevo registro";
}
