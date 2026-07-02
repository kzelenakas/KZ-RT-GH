from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.exports import render_csv, render_pdf

router = APIRouter(prefix="/api")


@router.get("/runs/{run_id}/export")
def export_run(run_id: str, request: Request, format: str = "csv", mode: str = "appraiser") -> Response:
    if format not in {"csv", "pdf"}:
        raise HTTPException(status_code=422, detail="format must be csv or pdf")
    if mode not in {"appraiser", "reviewer"}:
        raise HTTPException(status_code=422, detail="mode must be appraiser or reviewer")
    run = request.app.state.repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    stem = run["filename"].rsplit(".", 1)[0]
    if format == "csv":
        return Response(
            content=render_csv(run, mode),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="qc_{stem}_{mode}.csv"'},
        )
    return Response(
        content=render_pdf(run, mode),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="qc_{stem}_{mode}.pdf"'},
    )
