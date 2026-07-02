from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.ingest import IngestError, extract
from app.rules import evaluate

router = APIRouter(prefix="/api")


@router.post("/runs")
async def create_run(file: UploadFile, request: Request) -> dict:
    state = request.app.state
    data = await file.read()
    try:
        raw = extract(data, file.filename or "upload")
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    adapter = state.adapter
    structural_errors = adapter.validate(raw)
    normalized = adapter.normalize(raw)
    result = evaluate(normalized, state.rules)
    run_id = state.repo.save_run(
        filename=file.filename or "upload",
        file_hash=hashlib.sha256(data).hexdigest(),
        schema_version=adapter.schema_version,
        ruleset_version=state.ruleset_version,
        structural_errors=structural_errors,
        result=result,
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
