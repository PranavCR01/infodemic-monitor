// GET /v1/admin/evals (T63). Admin only; the server answers 401 without a valid token
// and 403 for any role below admin.
import { apiFetch } from "@/lib/api";
import { adaptEvals, type EvalsModel } from "./evals-adapter";
import type { RawEvalsResponse } from "./evals-types";

export type EvalsLoad =
  | { kind: "ok"; data: EvalsModel }
  | { kind: "sign-in" }
  | { kind: "forbidden" }
  | { kind: "error"; message: string };

export async function fetchEvals(): Promise<EvalsLoad> {
  try {
    const res = await apiFetch("/v1/admin/evals");
    if (res.status === 401) return { kind: "sign-in" };
    if (res.status === 403) return { kind: "forbidden" };
    if (!res.ok) return { kind: "error", message: "The evaluation list isn't available right now. Try again in a moment." };
    return { kind: "ok", data: adaptEvals((await res.json()) as RawEvalsResponse) };
  } catch {
    return { kind: "error", message: "The evaluation list couldn't be loaded: no connection." };
  }
}
