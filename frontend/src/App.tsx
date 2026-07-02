import { useEffect, useMemo, useState } from "react";
import { checkFinding, getRun, listRuns, reviewFinding, signOff, uploadReport } from "./api";
import { FindingCard, SEVERITY_LABEL, SEVERITY_ORDER, SEVERITY_STYLE } from "./FindingCard";
import type { Finding, Mode, Run, RunSummary, Severity } from "./types";

const SIGN_OFF_LABEL: Record<string, string> = {
  in_review: "In review",
  signed_off: "Signed off",
  returned: "Returned to appraiser",
};

export default function App() {
  const [run, setRun] = useState<Run | null>(null);
  const [mode, setMode] = useState<Mode>("appraiser");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [reviewerName, setReviewerName] = useState("");

  async function refreshHistory() {
    try {
      setHistory(await listRuns());
    } catch {
      /* backend not up yet */
    }
  }

  useEffect(() => {
    refreshHistory();
  }, []);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setRun(await uploadReport(file));
      await refreshHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onCheck(finding: Finding, checked: boolean) {
    if (!run) return;
    setRun(await checkFinding(run.id, finding.id, checked, mode));
  }

  async function onReview(finding: Finding, status: string, note: string | null) {
    if (!run) return;
    setRun(await reviewFinding(run.id, finding.id, status, note, mode));
    await refreshHistory();
  }

  async function onSignOff(state: string) {
    if (!run) return;
    setError(null);
    try {
      setRun(await signOff(run.id, state, reviewerName.trim() || null, mode));
      await refreshHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const grouped = useMemo(() => {
    if (!run) return [];
    const byCategory = new Map<string, Finding[]>();
    for (const f of run.findings) {
      byCategory.set(f.category, [...(byCategory.get(f.category) ?? []), f]);
    }
    return [...byCategory.entries()].map(([category, findings]) => ({
      category,
      findings: [...findings].sort(
        (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity),
      ),
    }));
  }, [run]);

  const actionable = run?.findings.filter((f) => f.severity !== "Advisory") ?? [];
  const addressed = actionable.filter((f) => f.appraiser_checked).length;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-900">UAD 3.6 QC</h1>
          <div className="flex rounded-lg border border-gray-300 text-sm">
            {(["appraiser", "reviewer"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-3 py-1.5 first:rounded-l-lg last:rounded-r-lg ${mode === m ? "bg-gray-900 text-white" : "bg-white text-gray-700"}`}
              >
                {m === "appraiser" ? "Appraiser" : "QD Reviewer"}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-6 px-6 py-8">
        <section className="rounded-lg border-2 border-dashed border-gray-300 bg-white p-8 text-center">
          <p className="text-sm text-gray-600">Upload a UAD 3.6 delivery (.zip) or report (.xml)</p>
          <input
            type="file"
            accept=".zip,.xml"
            disabled={busy}
            onChange={(e) => onFile(e.target.files?.[0])}
            className="mx-auto mt-3 block text-sm"
          />
          {busy && <p className="mt-2 text-sm text-gray-500">Checking report…</p>}
          {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
        </section>

        {run && (
          <>
            <section className="rounded-lg border border-gray-200 bg-white p-4 text-xs text-gray-600">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <span className="font-medium text-gray-900">{run.filename}</span>
                  {" · "}{new Date(run.created_at).toLocaleString()}
                  {" · schema "}{run.schema_version}
                  {" · rules "}{run.ruleset_version}
                </div>
                <span className="flex items-center gap-2 whitespace-nowrap">
                  <a
                    href={`/api/runs/${run.id}/export?format=pdf&mode=${mode}`}
                    className="rounded border border-gray-300 px-2 py-1 font-medium text-gray-700 hover:bg-gray-50"
                  >
                    PDF
                  </a>
                  <a
                    href={`/api/runs/${run.id}/export?format=csv&mode=${mode}`}
                    className="rounded border border-gray-300 px-2 py-1 font-medium text-gray-700 hover:bg-gray-50"
                  >
                    CSV
                  </a>
                  <span className="rounded bg-gray-100 px-2 py-1 font-medium text-gray-800">
                    {SIGN_OFF_LABEL[run.sign_off_state] ?? run.sign_off_state}
                    {run.reviewer_name ? ` · ${run.reviewer_name}` : ""}
                  </span>
                </span>
              </div>
            </section>

            <section className="flex gap-3">
              {SEVERITY_ORDER.map((s: Severity) => (
                <div key={s} className={`flex-1 rounded-lg border p-3 text-center ${SEVERITY_STYLE[s]}`}>
                  <div className="text-2xl font-bold">{run.counts[s] ?? 0}</div>
                  <div className="text-xs font-medium">{SEVERITY_LABEL[s]}s</div>
                </div>
              ))}
            </section>

            {run.structural_errors.length > 0 && (
              <section className="rounded-lg border border-purple-300 bg-purple-50 p-4">
                <h2 className="text-sm font-semibold text-purple-900">
                  Schema / structural issues ({run.structural_errors.length}) — checked before QC rules
                </h2>
                <ul className="mt-2 max-h-60 space-y-1 overflow-y-auto text-xs text-purple-800">
                  {run.structural_errors.map((e, i) => (
                    <li key={i}>[{e.code}{e.location ? ` @ ${e.location}` : ""}] {e.message}</li>
                  ))}
                </ul>
              </section>
            )}

            {mode === "appraiser" && actionable.length > 0 && (
              <section className="rounded-lg border border-gray-300 bg-white p-4">
                <h2 className="text-sm font-semibold text-gray-900">
                  Fix-it checklist — {addressed} of {actionable.length} addressed
                </h2>
                <p className="mt-1 text-xs text-gray-500">
                  Check items as you address them. Your checkmarks are saved and visible to the reviewer.
                </p>
              </section>
            )}

            {mode === "reviewer" && (
              <section className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-300 bg-white p-4">
                <span className="text-sm font-semibold text-gray-900">Sign-off:</span>
                <input
                  type="text"
                  value={reviewerName}
                  onChange={(e) => setReviewerName(e.target.value)}
                  placeholder="Reviewer name"
                  className="rounded border border-gray-300 px-2 py-1 text-sm"
                />
                <button
                  onClick={() => onSignOff("signed_off")}
                  className="rounded bg-green-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-800"
                >
                  Sign off
                </button>
                <button
                  onClick={() => onSignOff("returned")}
                  className="rounded bg-red-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-800"
                >
                  Return to appraiser
                </button>
                <button
                  onClick={() => onSignOff("in_review")}
                  className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
                >
                  Reopen
                </button>
              </section>
            )}

            {run.findings.length === 0 ? (
              <section className="rounded-lg border border-green-300 bg-green-50 p-6 text-center">
                <p className="font-semibold text-green-900">No issues found</p>
                <p className="mt-1 text-xs text-green-800">
                  {run.filename} · ruleset {run.ruleset_version} · schema {run.schema_version}
                </p>
              </section>
            ) : (
              grouped.map(({ category, findings }) => (
                <section key={category} className="space-y-2">
                  <h2 className="text-sm font-semibold text-gray-900">{category}</h2>
                  {findings.map((f) => (
                    <FindingCard key={f.id} finding={f} mode={mode} onCheck={onCheck} onReview={onReview} />
                  ))}
                </section>
              ))
            )}

            {mode === "reviewer" && run.rule_errors.length > 0 && (
              <section className="rounded-lg border border-gray-300 bg-gray-100 p-4">
                <h2 className="text-sm font-semibold text-gray-900">Rule execution errors ({run.rule_errors.length})</h2>
                <ul className="mt-2 space-y-1 text-xs text-gray-700">
                  {run.rule_errors.map((e, i) => (
                    <li key={i}>{e.rule_id}: [{e.error_type}] {e.detail}</li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}

        {history.length > 0 && (
          <section className="rounded-lg border border-gray-200 bg-white">
            <h2 className="border-b border-gray-200 px-4 py-3 text-sm font-semibold text-gray-900">
              Run history ({history.length})
            </h2>
            <ul className="divide-y divide-gray-100">
              {history.map((r) => (
                <li key={r.id}>
                  <button
                    onClick={async () => setRun(await getRun(r.id))}
                    className={`flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-xs hover:bg-gray-50 ${run?.id === r.id ? "bg-gray-50" : ""}`}
                  >
                    <span className="font-medium text-gray-900">{r.filename}</span>
                    <span className="text-gray-500">{new Date(r.created_at).toLocaleString()}</span>
                    <span className="flex items-center gap-1.5">
                      {SEVERITY_ORDER.filter((s) => (r.counts[s] ?? 0) > 0).map((s) => (
                        <span key={s} className={`rounded border px-1.5 py-0.5 ${SEVERITY_STYLE[s]}`}>
                          {r.counts[s]} {SEVERITY_LABEL[s]}
                        </span>
                      ))}
                      {SEVERITY_ORDER.every((s) => !(r.counts[s] ?? 0)) && (
                        <span className="rounded border border-green-300 bg-green-100 px-1.5 py-0.5 text-green-800">clean</span>
                      )}
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-700">
                        {SIGN_OFF_LABEL[r.sign_off_state] ?? r.sign_off_state}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  );
}
