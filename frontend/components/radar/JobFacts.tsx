import { formatSalary } from "../../lib/radar-format";
import { formatPublicationDate } from "../../lib/tracking-dates";
import type { Job } from "../../types";

type OfferFacts = Pick<Job, "district" | "location" | "work_mode" | "salary_min" | "salary_max" | "salary_currency" | "published_at" | "application_status">;

export default function JobFacts({ job }: { job: OfferFacts }) {
  const mode = job.work_mode === "hybrid" ? "Híbrido" : job.work_mode === "remote" ? "Remoto" : job.work_mode === "onsite" ? "Presencial" : "No indicada";
  const status = job.application_status === "closed" ? "Cerrada" : job.application_status === "expired" ? "Vencida" : job.application_status === "open" ? "Abierta según última consulta" : "Vigencia sin verificar";

  return <div className="popover-grid">
    <div><span>Ubicación</span><strong>{job.district || job.location || "Pendiente"}</strong></div>
    <div><span>Modalidad</span><strong>{mode}</strong></div>
    <div><span>Salario</span><strong>{formatSalary(job)}</strong></div>
    <div><span>Publicado</span><strong>{formatPublicationDate(job.published_at)}</strong></div>
    <div><span>Estado de publicación</span><strong>{status}</strong></div>
  </div>;
}
