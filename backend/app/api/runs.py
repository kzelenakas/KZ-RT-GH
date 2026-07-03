from __future__ import annotations

import csv
import hashlib
import io
import logging

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app import config
from app.ingest import IngestError, extract
from app.models import RunResult
from app.rules import evaluate

router = APIRouter(prefix="/api")
logger = logging.getLogger("qc.runs")

RULES_LOG_NAME = "rules_log.csv"


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
