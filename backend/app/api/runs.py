from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app import config
from app.ingest import IngestError, extract
from app.rules import evaluate

router = APIRouter(prefix="/api")


def _retain_original(run_id: str, filename: str, data: bytes) -> None:
    """Keep the uploaded original (spec: full retention). Filesystem-backed so a
    GCS FUSE volume makes it durable on Cloud Run without code changes."""
    safe_name = filename.replace("/", "_").replace("\\", "_")
    target_dir = config.FILES_DIR / run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / safe_name).write_bytes(data)


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
