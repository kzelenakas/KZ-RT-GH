import type { Run } from "./types";

export async function uploadReport(file: File): Promise<Run> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch("/api/runs", { method: "POST", body });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? "Upload failed");
  }
  return res.json();
}
