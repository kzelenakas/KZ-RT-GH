import type { Mode, Run, RunSummary } from "./types";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "Request failed");
  }
  return res.json();
}

function roleHeaders(mode: Mode): Record<string, string> {
  return { "X-QC-Role": mode };
}

export async function uploadReport(file: File): Promise<Run> {
  const body = new FormData();
  body.append("file", file);
  return handle(await fetch("/api/runs", { method: "POST", body }));
}

export async function listRuns(): Promise<RunSummary[]> {
  return handle(await fetch("/api/runs"));
}

export async function getRun(id: string): Promise<Run> {
  return handle(await fetch(`/api/runs/${id}`));
}

export async function checkFinding(runId: string, findingId: number, checked: boolean, mode: Mode): Promise<Run> {
  return handle(await fetch(`/api/runs/${runId}/findings/${findingId}/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...roleHeaders(mode) },
    body: JSON.stringify({ checked }),
  }));
}

export async function reviewFinding(
  runId: string, findingId: number, status: string, note: string | null, mode: Mode,
): Promise<Run> {
  return handle(await fetch(`/api/runs/${runId}/findings/${findingId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...roleHeaders(mode) },
    body: JSON.stringify({ status, note }),
  }));
}

export async function signOff(runId: string, state: string, reviewer: string | null, mode: Mode): Promise<Run> {
  return handle(await fetch(`/api/runs/${runId}/sign-off`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...roleHeaders(mode) },
    body: JSON.stringify({ state, reviewer }),
  }));
}
