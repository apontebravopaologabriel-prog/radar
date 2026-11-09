import type { paths } from "./api-schema";
import { requestJson } from "./http";

type StartRefresh = paths["/api/refresh"]["post"];
type RefreshRequest = StartRefresh["requestBody"]["content"]["application/json"];
type RefreshAccepted = StartRefresh["responses"][202]["content"]["application/json"];
export type RefreshState = paths["/api/refresh/status"]["get"]["responses"][200]["content"]["application/json"];

export function startRefresh(body: RefreshRequest): Promise<RefreshAccepted> {
  return requestJson("/api/refresh", { method: "POST", body: JSON.stringify(body) });
}

export function fetchRefreshStatus(): Promise<RefreshState> {
  return requestJson("/api/refresh/status");
}
