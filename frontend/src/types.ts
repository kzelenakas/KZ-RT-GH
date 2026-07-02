export type Severity = "HardStop" | "Warning" | "Advisory";
export type Mode = "appraiser" | "reviewer";

export interface Finding {
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

export interface Run {
  id: string;
  filename: string;
  file_hash: string;
  created_at: string;
  schema_version: string;
  ruleset_version: string;
  counts: Record<Severity, number>;
  structural_errors: StructuralError[];
  findings: Finding[];
  rule_errors: RuleError[];
}
