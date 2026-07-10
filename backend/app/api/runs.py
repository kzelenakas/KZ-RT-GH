from __future__ import annotations

import csv
import hashlib
import io
import logging

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

import collateral_risk_engine
from app import config
from app.ingest import IngestError, extract
from app.models import Finding, RuleError, RunResult, Severity
from app.rules import evaluate

router = APIRouter(prefix="/api")
logger = logging.getLogger("qc.runs")

RULES_LOG_NAME = "rules_log.csv"

# collateral_risk_engine finding severities -> backend Severity. The two engines'
# finding shapes are not aligned: collateral_risk_engine uses "Fatal"/"Advisory"
# (rules.json), not the backend's HardStop/Warning/Advisory enum.
_CR_SEVERITY_MAP = {"Fatal": Severity.HARD_STOP, "Advisory": Severity.ADVISORY}


def _cr_finding_to_finding(raw: dict) -> Finding:
    """Adapt one collateral_risk_engine finding dict ({rule_id, category, severity,
    description, citation, values}) into the backend's Finding model.

    Mismatches handled here:
    - severity: "Fatal" isn't a valid Severity member; mapped to HARD_STOP. Any other
      unrecognized value falls back to ADVISORY rather than raising -- every severity
      in the current rules.json is "Fatal" or "Advisory", so this is a defensive-only
      branch, not an expected path.
    - message_appraiser/message_reviewer: collateral_risk_engine only has a single
      `description`, no appraiser/reviewer split. Both fields derive from it, mirroring
      the `rule.messages.appraiser or rule.messages.reviewer or rule.description`
      fallback in app/rules/engine.py.
    - values: collateral_risk_engine's values can hold float/int (e.g. geo_proximity's
      distance_ft/threshold_ft); Finding.values requires str | None, and pydantic v2
      does not coerce numbers into str for this field (verified empirically), so every
      value is stringified explicitly.
    - field_path: no single natural field for a geo_proximity rule (it's a live lookup,
      not one XML field); left empty, matching Finding's default and the field's
      documented non-load-bearing status for these rules.
    """
    severity = _CR_SEVERITY_MAP.get(raw.get("severity"), Severity.ADVISORY)
    description = raw.get("description") or ""
    values = {k: (None if v is None else str(v)) for k, v in (raw.get("values") or {}).items()}
    return Finding(
        rule_id=raw["rule_id"],
        category=raw.get("category", ""),
        severity=severity,
        message_appraiser=description,
        message_reviewer=description,
        field_path="",
        values=values,
        citation=raw.get("citation"),
    )


def _retain_original(run_id: str, filename: str, data: bytes) -> None:
    """Keep the uploaded original (spec: full retention). Filesystem-backed so a
    GCS FUSE volume makes it durable on Cloud Run without code changes."""
    safe_name = filename.replace("/", "_").replace("\\", "_")
    target_dir = config.FILES_DIR / run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / safe_name).write_bytes(data)


def _write_rules_log(run_id: str, filename: str, ruleset_version: str, result: RunResult) -> None:
    """One CSV per run: every rule considered and what happened to it.
    Lives next to the retained original, so the GCS mount makes it durable too."""
    target_dir = config.FILES_DIR / run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["run_id", "source_file", "ruleset_version", "rule_id", "category",
                     "severity", "status", "detail"])
    for t in result.trace:
        writer.writerow([run_id, filename, ruleset_version, t.rule_id, t.category,
                         t.severity.value, t.status, t.detail])
    (target_dir / RULES_LOG_NAME).write_text(buf.getvalue(), encoding="utf-8")


@router.post("/runs")
async def create_run(file: UploadFile, request: Request, profile: str | None = None) -> dict:
    state = request.app.state
    data = await file.read()
    try:
        raw = extract(data, file.filename or "upload")
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    adapter = state.adapter
    structural_errors = adapter.validate(raw)
    normalized = adapter.normalize(raw)
    rules, ruleset_version = state.rules_repo.active_rules(profile)
    result = evaluate(normalized, rules, ai_backend=state.ai_backend)
    try:
        # collateral_risk_engine works off the raw XML directly (geo_proximity rules
        # need live coordinates, not the normalized field map), and is a separate
        # ruleset/package entirely -- see collateral_risk_engine/README.md. Findings
        # only are merged into the same RunResult; collateral_risk_engine's rule
        # evaluations are intentionally NOT added to result.trace (that CSV's contract
        # -- one row per H-1 rule considered -- stays as-is; a combined audit trail
        # across both rulesets is a separate, not-yet-decided follow-up).
        cr_findings = [_cr_finding_to_finding(f) for f in collateral_risk_engine.evaluate(raw.xml_bytes)]
    except Exception as exc:  # noqa: BLE001 - collateral-risk checks must never kill the run
        detail = f"{type(exc).__name__}: {exc}"
        result.rule_errors.append(RuleError(
            rule_id="collateral_risk_engine", error_type="collateral_risk_error", detail=detail,
        ))
        logger.warning("collateral_risk_engine.evaluate failed: %s", detail)
    else:
        result.findings.extend(cr_findings)
    try:
        # Phase 2/3 -- photo quality + face-detection redaction prompt. Same
        # never-kill-the-run guard, same finding adapter (values dict already
        # stringifies cleanly; photo findings add a "photo" key with the
        # filename, harmless extra key for _cr_finding_to_finding).
        cr_photo_findings = [_cr_finding_to_finding(f) for f in collateral_risk_engine.evaluate_photos(raw.images)]
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {exc}"
        result.rule_errors.append(RuleError(
            rule_id="collateral_risk_engine_photos", error_type="collateral_risk_error", detail=detail,
        ))
        logger.warning("collateral_risk_engine.evaluate_photos failed: %s", detail)
    else:
        result.findings.extend(cr_photo_findings)
    run_id = state.repo.save_run(
        filename=file.filename or "upload",
        file_hash=hashlib.sha256(data).hexdigest(),
        schema_version=adapter.schema_version,
        ruleset_version=ruleset_version,
        structural_errors=structural_errors,
        result=result,
    )
    _retain_original(run_id, file.filename or "upload", data)
    _write_rules_log(run_id, file.filename or "upload", ruleset_version, result)
    counts = {"pass": 0, "finding": 0, "error": 0, "skipped": 0}
    for t in result.trace:
        counts[t.status] = counts.get(t.status, 0) + 1
    logger.info(
        "run %s file=%s ruleset=%s rules_evaluated=%d pass=%d findings=%d errors=%d skipped=%d",
        run_id, file.filename or "upload", ruleset_version,
        counts["pass"] + counts["finding"] + counts["error"],
        counts["pass"], counts["finding"], counts["error"], counts["skipped"],
    )
    return state.repo.get_run(run_id)


@router.get("/runs")
def list_runs(request: Request) -> list[dict]:
    return request.app.state.repo.list_runs()


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> dict:
    payload = request.app.state.repo.get_run(run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return payload


@router.get("/runs/{run_id}/rules-log")
def rules_log(run_id: str, request: Request) -> FileResponse:
    if request.app.state.repo.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    path = config.FILES_DIR / run_id / RULES_LOG_NAME
    if not path.exists():
        raise HTTPException(status_code=404, detail="Rules log not found for this run")
    return FileResponse(path, media_type="text/csv", filename=f"rules_log_{run_id}.csv")
