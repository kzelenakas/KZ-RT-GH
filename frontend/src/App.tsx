import { useMemo, useState } from "react";
import { uploadReport } from "./api";
import type { Finding, Mode, Run, Severity } from "./types";

const SEVERITY_ORDER: Severity[] = ["HardStop", "Warning", "Advisory"];
const SEVERITY_STYLE: Record<Severity, string> = {
  HardStop: "bg-red-100 text-red-800 border-red-300",
  Warning: "bg-amber-100 text-amber-800 border-amber-300",
  Advisory: "bg-sky-100 text-sky-800 border-sky-300",
};
const SEVERITY_LABEL: Record<Severity, string> = {
  HardStop: "Hard Stop",
  Warning: "Warning",
  Advisory: "Advisory",
};

function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`inline-block rounded border px-2 py-0.5 text-xs font-semibold ${SEVERITY_STYLE[severity]}`}>
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

function FindingCard({ finding, mode }: { finding: Finding; mode: Mode }) {
  const message = mode === "appraiser" ? finding.message_appraiser : finding.message_reviewer;
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <SeverityBadge severity={finding.severity} />
        <span className="text-xs text-gray-500">{finding.rule_id}</span>
      </div>
      <p className="mt-2 text-sm text-gray-900">{message}</p>
      <dl className="mt-2 space-y-0.5 text-xs text-gray-600">
        {finding.section && (
          <div>
            <dt className="inline font-medium">Location: </dt>
            <dd className="inline">{finding.section}{finding.xpath ? ` — ${finding.xpath}` : ""}</dd>
          </div>
        )}
        {Object.entries(finding.values).map(([k, v]) => (
          <div key={k}>
            <dt className="inline font-medium">Value: </dt>
            <dd className="inline">{k} = {v === null || v === "" ? "(blank)" : v}</dd>
          </div>
        ))}
        {mode === "reviewer" && finding.citation && (
          <div>
            <dt className="inline font-medium">Citation: </dt>
            <dd className="inline">{finding.citation}</dd>
          </div>
        )}
      </dl>
    </div>
  );
}

export default function App() {
  const [run, setRun] = useState<Run | null>(null);
  const [mode, setMode] = useState<Mode>("appraiser");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setRun(await uploadReport(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
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
              <span className="font-medium text-gray-900">{run.filename}</span>
              {" · "}{new Date(run.created_at).toLocaleString()}
              {" · schema "}{run.schema_version}
              {" · rules "}{run.ruleset_version}
            </section>

            <section className="flex gap-3">
              {SEVERITY_ORDER.map((s) => (
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
                  {findings.map((f, i) => (
                    <FindingCard key={`${f.rule_id}-${i}`} finding={f} mode={mode} />
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
      </main>
    </div>
  );
}
