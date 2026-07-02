import { useEffect, useMemo, useState } from "react";
import {
  archiveRule, exportRuleset, importRuleset, listAdminRules, listProfiles,
  saveProfile, saveRule, toggleRule,
} from "./adminApi";
import type { AdminRule, Profile } from "./adminApi";

type Tab = "all" | "enabled" | "needs_encoding" | "profiles";

const SEVERITIES = ["HardStop", "Warning", "Advisory"] as const;
const PAGE_SIZE = 50;

export function AdminPanel() {
  const [tab, setTab] = useState<Tab>("all");
  const [rules, setRules] = useState<AdminRule[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [editing, setEditing] = useState<AdminRule | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      if (tab === "profiles") {
        setProfiles(await listProfiles());
      } else {
        setRules(await listAdminRules(tab));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
    setPage(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rules;
    return rules.filter((r) =>
      r.rule_id.toLowerCase().includes(q) ||
      r.category.toLowerCase().includes(q) ||
      (r.description || "").toLowerCase().includes(q),
    );
  }, [rules, search]);

  const pageRules = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  async function onToggle(rule: AdminRule) {
    try {
      const updated = await toggleRule(rule.rule_id, !rule.enabled);
      setRules((rs) => rs.map((r) => (r.rule_id === rule.rule_id ? updated : r)));
      setStatus(`${rule.rule_id} ${updated.enabled ? "turned ON" : "turned OFF"}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function onSaveEdit() {
    if (!editing) return;
    setError(null);
    try {
      const updated = await saveRule(editing);
      setRules((rs) => rs.map((r) => (r.rule_id === updated.rule_id ? updated : r)));
      setStatus(`${updated.rule_id} saved`);
      setEditing(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function onArchive(rule: AdminRule) {
    if (!window.confirm(`Remove rule ${rule.rule_id}? It is archived (kept in history), not deleted.`)) return;
    try {
      await archiveRule(rule.rule_id);
      setRules((rs) => rs.filter((r) => r.rule_id !== rule.rule_id));
      setStatus(`${rule.rule_id} archived`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function onExport() {
    const data = await exportRuleset();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "qc_ruleset_export.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function onImport(file: File | undefined) {
    if (!file) return;
    setError(null);
    try {
      const data = JSON.parse(await file.text());
      const result = await importRuleset(data, false);
      setStatus(`Imported/updated ${result.imported} rules`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-center gap-2">
          {(["all", "enabled", "needs_encoding", "profiles"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded px-3 py-1.5 text-sm font-medium ${tab === t ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}
            >
              {t === "all" ? "All rules" : t === "enabled" ? "Enabled" : t === "needs_encoding" ? "Needs encoding" : "Client profiles"}
            </button>
          ))}
          <span className="ml-auto flex items-center gap-2">
            <button onClick={onExport} className="rounded border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50">
              Export rules
            </button>
            <label className="cursor-pointer rounded border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50">
              Import rules
              <input type="file" accept=".json" className="hidden" onChange={(e) => onImport(e.target.files?.[0])} />
            </label>
          </span>
        </div>
        {tab !== "profiles" && (
          <input
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            placeholder="Search by rule ID, category, or description…"
            className="mt-3 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
        )}
        {status && <p className="mt-2 text-xs text-green-700">{status}</p>}
        {error && <p className="mt-2 text-xs text-red-700">{error}</p>}
      </section>

      {tab === "profiles" ? (
        <ProfilesPanel profiles={profiles} onSaved={refresh} />
      ) : (
        <section className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2 text-xs text-gray-600">
            <span>{filtered.length} rules</span>
            <span className="flex items-center gap-2">
              <button disabled={page === 0} onClick={() => setPage(page - 1)} className="rounded border border-gray-300 px-2 py-0.5 disabled:opacity-40">←</button>
              page {page + 1} / {pageCount}
              <button disabled={page >= pageCount - 1} onClick={() => setPage(page + 1)} className="rounded border border-gray-300 px-2 py-0.5 disabled:opacity-40">→</button>
            </span>
          </div>
          <ul className="divide-y divide-gray-100">
            {pageRules.map((rule) => (
              <li key={rule.rule_id} className="px-4 py-2.5 text-xs">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => onToggle(rule)}
                    className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${rule.enabled ? "bg-green-600" : "bg-gray-300"}`}
                    title={rule.enabled ? "Rule is ON — click to turn off" : "Rule is OFF — click to turn on"}
                  >
                    <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${rule.enabled ? "left-4.5" : "left-0.5"}`} />
                  </button>
                  <span className="w-24 shrink-0 font-mono font-medium text-gray-900">{rule.rule_id}</span>
                  <span className={`w-20 shrink-0 font-medium ${rule.severity === "HardStop" ? "text-red-700" : rule.severity === "Warning" ? "text-amber-700" : "text-sky-700"}`}>
                    {rule.severity === "HardStop" ? "Hard Stop" : rule.severity}
                  </span>
                  <span className="w-40 shrink-0 truncate text-gray-500">{rule.category}</span>
                  <span className="min-w-0 flex-1 truncate text-gray-700">{rule.description}</span>
                  {rule.logic?.type === "needs_encoding" && (
                    <span className="shrink-0 rounded bg-orange-100 px-1.5 py-0.5 text-orange-800" title="This rule's logic hasn't been encoded yet — it never runs until it is.">
                      needs encoding
                    </span>
                  )}
                  <button onClick={() => setEditing(structuredClone(rule))} className="shrink-0 rounded border border-gray-300 px-2 py-0.5 text-gray-700 hover:bg-gray-50">
                    Edit
                  </button>
                  <button onClick={() => onArchive(rule)} className="shrink-0 rounded border border-red-200 px-2 py-0.5 text-red-700 hover:bg-red-50">
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {editing && (
        <section className="rounded-lg border-2 border-gray-900 bg-white p-4">
          <h3 className="text-sm font-semibold text-gray-900">Edit rule {editing.rule_id}</h3>
          <div className="mt-3 grid gap-3 text-xs">
            <label className="grid gap-1">
              <span className="font-medium text-gray-700">Severity</span>
              <select
                value={editing.severity}
                onChange={(e) => setEditing({ ...editing, severity: e.target.value as AdminRule["severity"] })}
                className="rounded border border-gray-300 px-2 py-1.5"
              >
                {SEVERITIES.map((s) => <option key={s} value={s}>{s === "HardStop" ? "Hard Stop (must fix)" : s === "Warning" ? "Warning (should fix)" : "Advisory (informational)"}</option>)}
              </select>
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-gray-700">Category</span>
              <input value={editing.category} onChange={(e) => setEditing({ ...editing, category: e.target.value })} className="rounded border border-gray-300 px-2 py-1.5" />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-gray-700">Description (what is checked)</span>
              <input value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} className="rounded border border-gray-300 px-2 py-1.5" />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-gray-700">Message for appraisers (coaching tone)</span>
              <textarea
                value={editing.messages?.appraiser ?? ""}
                onChange={(e) => setEditing({ ...editing, messages: { ...editing.messages, appraiser: e.target.value || null } })}
                rows={2} className="rounded border border-gray-300 px-2 py-1.5"
              />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-gray-700">Message for reviewers (audit tone)</span>
              <textarea
                value={editing.messages?.reviewer ?? ""}
                onChange={(e) => setEditing({ ...editing, messages: { ...editing.messages, reviewer: e.target.value || null } })}
                rows={2} className="rounded border border-gray-300 px-2 py-1.5"
              />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-gray-700">
                Rule logic (advanced — JSON). Types: field_present, regex_match, field_in_set, numeric_range, ai, needs_encoding.
              </span>
              <textarea
                value={JSON.stringify(editing.logic, null, 2)}
                onChange={(e) => {
                  try {
                    setEditing({ ...editing, logic: JSON.parse(e.target.value) });
                  } catch {
                    /* keep typing; invalid JSON not applied */
                  }
                }}
                rows={5} className="rounded border border-gray-300 px-2 py-1.5 font-mono"
              />
            </label>
            <div className="flex gap-2">
              <button onClick={onSaveEdit} className="rounded bg-gray-900 px-3 py-1.5 font-medium text-white">Save</button>
              <button onClick={() => setEditing(null)} className="rounded border border-gray-300 px-3 py-1.5 text-gray-700">Cancel</button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function ProfilesPanel({ profiles, onSaved }: { profiles: Profile[]; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [disabledIds, setDisabledIds] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSave() {
    setError(null);
    try {
      const ids = disabledIds.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
      await saveProfile(name.trim(), description.trim(), ids);
      setName(""); setDescription(""); setDisabledIds("");
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-gray-900">Client profiles</h3>
        <p className="mt-1 text-xs text-gray-500">
          A profile turns specific rules OFF for a client. Pick the profile when uploading a report; everything else stays the same.
        </p>
        <ul className="mt-3 space-y-2">
          {profiles.map((p) => (
            <li key={p.id} className="rounded border border-gray-200 p-3 text-xs">
              <div className="font-medium text-gray-900">{p.name}</div>
              {p.description && <div className="text-gray-600">{p.description}</div>}
              <div className="mt-1 text-gray-500">
                Rules turned off: {p.disabled_rule_ids.length ? p.disabled_rule_ids.join(", ") : "none"}
              </div>
              <button
                onClick={() => { setName(p.name); setDescription(p.description); setDisabledIds(p.disabled_rule_ids.join(", ")); }}
                className="mt-2 rounded border border-gray-300 px-2 py-0.5 text-gray-700 hover:bg-gray-50"
              >
                Edit
              </button>
            </li>
          ))}
          {profiles.length === 0 && <li className="text-xs text-gray-500">No profiles yet.</li>}
        </ul>
      </div>
      <div className="rounded-lg border border-gray-200 bg-white p-4 text-xs">
        <h3 className="text-sm font-semibold text-gray-900">New / edit profile</h3>
        <div className="mt-3 grid gap-3">
          <label className="grid gap-1">
            <span className="font-medium text-gray-700">Profile name (e.g. the client or lender)</span>
            <input value={name} onChange={(e) => setName(e.target.value)} className="rounded border border-gray-300 px-2 py-1.5" />
          </label>
          <label className="grid gap-1">
            <span className="font-medium text-gray-700">Description</span>
            <input value={description} onChange={(e) => setDescription(e.target.value)} className="rounded border border-gray-300 px-2 py-1.5" />
          </label>
          <label className="grid gap-1">
            <span className="font-medium text-gray-700">Rule IDs to turn OFF (comma-separated, e.g. UAD1008, UAD1009)</span>
            <textarea value={disabledIds} onChange={(e) => setDisabledIds(e.target.value)} rows={2} className="rounded border border-gray-300 px-2 py-1.5 font-mono" />
          </label>
          <div>
            <button onClick={onSave} disabled={!name.trim()} className="rounded bg-gray-900 px-3 py-1.5 font-medium text-white disabled:opacity-40">
              Save profile
            </button>
            {error && <span className="ml-2 text-red-700">{error}</span>}
          </div>
        </div>
      </div>
    </section>
  );
}
