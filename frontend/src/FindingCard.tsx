import { useState } from "react";
import type { Finding, Mode, Severity } from "./types";

export const SEVERITY_ORDER: Severity[] = ["HardStop", "Warning", "Advisory"];
export const SEVERITY_STYLE: Record<Severity, string> = {
  HardStop: "bg-red-100 text-red-800 border-red-300",
  Warning: "bg-amber-100 text-amber-800 border-amber-300",
  Advisory: "bg-sky-100 text-sky-800 border-sky-300",
};
export const SEVERITY_LABEL: Record<Severity, string> = {
  HardStop: "Hard Stop",
  Warning: "Warning",
  Advisory: "Advisory",
};

const VERDICTS: Record<Severity, { value: string; label: string }[]> = {
  HardStop: [
    { value: "resolved", label: "Resolved" },
    { value: "fail", label: "Fail — return" },
  ],
  Warning: [
    { value: "pass", label: "Pass" },
    { value: "fail", label: "Fail — return" },
    { value: "conditional_pass", label: "Conditional pass" },
  ],
  Advisory: [{ value: "acknowledged", label: "Acknowledge" }],
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending review",
  resolved: "Resolved",
  pass: "Pass",
  fail: "Fail — returned",
  conditional_pass: "Conditional pass",
  acknowledged: "Acknowledged",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`inline-block rounded border px-2 py-0.5 text-xs font-semibold ${SEVERITY_STYLE[severity]}`}>
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

interface Props {
  finding: Finding;
  mode: Mode;
  onCheck: (finding: Finding, checked: boolean) => void;
  onReview: (finding: Finding, status: string, note: string | null) => Promise<void>;
}

export function FindingCard({ finding, mode, onCheck, onReview }: Props) {
  const [note, setNote] = useState(finding.reviewer_note ?? "");
  const [reviewError, setReviewError] = useState<string | null>(null);
  const message = mode === "appraiser" ? finding.message_appraiser : finding.message_reviewer;
  const actionable = finding.severity !== "Advisory";

  async function review(status: string) {
    setReviewError(null);
    try {
      await onReview(finding, status, note.trim() ? note.trim() : null);
    } catch (e) {
      setReviewError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        {mode === "appraiser" && actionable && (
          <input
            type="checkbox"
            checked={finding.appraiser_checked}
            onChange={(e) => onCheck(finding, e.target.checked)}
            className="h-4 w-4"
            aria-label="Mark as addressed"
          />
        )}
        <SeverityBadge severity={finding.severity} />
        <span className="text-xs text-gray-500">{finding.rule_id}</span>
        {mode === "reviewer" && finding.appraiser_checked && (
          <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-800">appraiser: addressed</span>
        )}
        {finding.reviewer_status !== "pending" && (
          <span className="ml-auto rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">
            {STATUS_LABEL[finding.reviewer_status] ?? finding.reviewer_status}
          </span>
        )}
      </div>
      <p className={`mt-2 text-sm text-gray-900 ${mode === "appraiser" && finding.appraiser_checked ? "line-through opacity-60" : ""}`}>
        {message}
      </p>
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
            <dd className="inline">{v === null || v === "" ? "(blank)" : v}</dd>
          </div>
        ))}
        {mode === "reviewer" && finding.citation && (
          <div>
            <dt className="inline font-medium">Citation: </dt>
            <dd className="inline">{finding.citation}</dd>
          </div>
        )}
        {finding.reviewer_note && (
          <div>
            <dt className="inline font-medium">Reviewer note: </dt>
            <dd className="inline">{finding.reviewer_note}</dd>
          </div>
        )}
      </dl>
      {mode === "reviewer" && (
        <div className="mt-3 border-t border-gray-100 pt-3">
          <div className="flex flex-wrap items-center gap-2">
            {VERDICTS[finding.severity].map((v) => (
              <button
                key={v.value}
                onClick={() => review(v.value)}
                className={`rounded border px-2.5 py-1 text-xs font-medium ${
                  finding.reviewer_status === v.value
                    ? "border-gray-900 bg-gray-900 text-white"
                    : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                }`}
              >
                {v.label}
              </button>
            ))}
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Reviewer note (required for conditional pass)"
              className="min-w-48 flex-1 rounded border border-gray-300 px-2 py-1 text-xs"
            />
          </div>
          {reviewError && <p className="mt-1 text-xs text-red-700">{reviewError}</p>}
        </div>
      )}
    </div>
  );
}
