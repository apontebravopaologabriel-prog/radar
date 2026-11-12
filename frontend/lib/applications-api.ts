import type { paths } from "./api-schema";
import { requestJson } from "./http";

type ApplicationList = paths["/api/applications"]["get"]["responses"][200]["content"]["application/json"];
type ApplicationRoute = paths["/api/applications/{job_id}"];
type ApplicationUpdate = ApplicationRoute["put"]["requestBody"]["content"]["application/json"];
type ApplicationUpdated = ApplicationRoute["put"]["responses"][200]["content"]["application/json"];

export type TrackedApplication = ApplicationList["applications"][number];

export async function fetchApplications(signal?: AbortSignal): Promise<TrackedApplication[]> {
  return (await requestJson<ApplicationList>("/api/applications", { signal })).applications;
}

type TrackingApplications = paths["/api/applications/tracking"]["get"]["responses"][200]["content"]["application/json"];

export type TrackingApplicationItem = TrackingApplications["applications"][number];

export function fetchTrackingApplications(signal?: AbortSignal): Promise<TrackingApplications> {
  return requestJson("/api/applications/tracking", { signal });
}

export function updateApplication(jobId: string, status: ApplicationUpdate["status"], notes?: string | null): Promise<ApplicationUpdated> {
  const body: ApplicationUpdate = { status, notes };
  return requestJson(`/api/applications/${encodeURIComponent(jobId)}`, { method: "PUT", body: JSON.stringify(body) });
}
