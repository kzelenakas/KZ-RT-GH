export type Severity = "HardStop" | "Warning" | "Advisory";
export type Mode = "appraiser" | "reviewer";

export interface Finding {
  id: number;
  rule_id: string;
  category: string;
  severity: Severity;
  message_appraiser: string;
  message_reviewer: string;
  field_path: string;
  xpath: string | null;
  section: string | null;
  values: Record<string, string | null>;
  citation: string | null;
  appraiser_checked: boolean;
  reviewer_status: string;
  reviewer_note: string | null;
  reviewed_at: string | null;
}

export interface StructuralError {
  code: string;
  message: string;
  location: string | null;
}

export interface RuleError {
  rule_id: string;
  error_type: string;
  detail: string;
}

export interface RunSummary {
  id: string;
  filename: string;
  created_at: string;
  schema_version: string;
  ruleset_version: string;
  sign_off_state: string;
  reviewer_name: string | null;
  counts: Record<Severity, number>;
}

export interface Run extends RunSummary {
  file_hash: string;
  structural_errors: StructuralError[];
  findings: Finding[];
  rule_errors: RuleError[];
}
