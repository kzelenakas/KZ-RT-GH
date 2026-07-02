const ADMIN = { "X-QC-Role": "admin" };

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "Request failed");
  }
  return res.json();
}

export interface AdminRule {
  rule_id: string;
  category: string;
  description: string;
  severity: "HardStop" | "Warning" | "Advisory";
  enabled: boolean;
  logic: Record<string, unknown> & { type?: string };
  citation?: string | null;
  messages?: { appraiser?: string | null; reviewer?: string | null };
  [key: string]: unknown;
}

export interface Profile {
  id: number;
  name: string;
  description: string;
  disabled_rule_ids: string[];
}

export async function listAdminRules(status: string): Promise<AdminRule[]> {
  return handle(await fetch(`/api/admin/rules?status=${status}`, { headers: ADMIN }));
}

export async function saveRule(rule: AdminRule): Promise<AdminRule> {
  return handle(await fetch(`/api/admin/rules/${encodeURIComponent(rule.rule_id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...ADMIN },
    body: JSON.stringify(rule),
  }));
}

export async function toggleRule(ruleId: string, enabled: boolean): Promise<AdminRule> {
  return handle(await fetch(`/api/admin/rules/${encodeURIComponent(ruleId)}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...ADMIN },
    body: JSON.stringify({ enabled }),
  }));
}

export async function archiveRule(ruleId: string): Promise<void> {
  await handle(await fetch(`/api/admin/rules/${encodeURIComponent(ruleId)}/archive`, {
    method: "POST", headers: ADMIN,
  }));
}

export async function listProfiles(): Promise<Profile[]> {
  return handle(await fetch("/api/admin/profiles", { headers: ADMIN }));
}

export async function saveProfile(name: string, description: string, disabledRuleIds: string[]): Promise<Profile> {
  return handle(await fetch("/api/admin/profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...ADMIN },
    body: JSON.stringify({ name, description, disabled_rule_ids: disabledRuleIds }),
  }));
}

export async function exportRuleset(): Promise<unknown> {
  return handle(await fetch("/api/admin/export", { headers: ADMIN }));
}

export async function importRuleset(ruleset: unknown, replace: boolean): Promise<{ imported: number }> {
  return handle(await fetch("/api/admin/import", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...ADMIN },
    body: JSON.stringify({ ruleset, replace }),
  }));
}
