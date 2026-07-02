from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api")

# Reviewer verdicts allowed per severity (spec: Hard Stop -> resolved/fail;
# Warning -> pass/fail/conditional pass (+ required comment); Advisory -> ack).
REVIEW_CHOICES = {
    "HardStop": {"resolved", "fail"},
    "Warning": {"pass", "fail", "conditional_pass"},
    "Advisory": {"acknowledged"},
}


def _role(x_qc_role: str | None) -> str:
    # Beta role model: in-app role switcher sends this header. IAP identity
    # replaces/augments it at GCP deploy time; the gate stays server-side.
    return (x_qc_role or "appraiser").lower()


def _require_reviewer(role: str) -> None:
    if role != "reviewer":
        raise HTTPException(status_code=403, detail="Reviewer role required")


class CheckBody(BaseModel):
    checked: bool


class ReviewBody(BaseModel):
    status: str
    note: str | None = None


class SignOffBody(BaseModel):
    state: str
    reviewer: str | None = None


@router.post("/runs/{run_id}/findings/{finding_id}/check")
def check_finding(
    run_id: str, finding_id: int, body: CheckBody, request: Request,
    x_qc_role: str | None = Header(default=None),
) -> dict:
    role = _role(x_qc_role)
    payload = request.app.state.repo.set_finding_check(run_id, finding_id, body.checked, role)
    if payload is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return payload


@router.post("/runs/{run_id}/findings/{finding_id}/review")
def review_finding(
    run_id: str, finding_id: int, body: ReviewBody, request: Request,
    x_qc_role: str | None = Header(default=None),
) -> dict:
    role = _role(x_qc_role)
    _require_reviewer(role)
    repo = request.app.state.repo
    severity = repo.finding_severity(run_id, finding_id)
    if severity is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    allowed = REVIEW_CHOICES.get(severity, set())
    if body.status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Status {body.status!r} not allowed for {severity} findings. Allowed: {sorted(allowed)}",
        )
    if body.status == "conditional_pass" and not (body.note or "").strip():
        raise HTTPException(status_code=422, detail="Conditional pass requires a reviewer comment")
    return repo.review_finding(run_id, finding_id, body.status, body.note, role)


@router.post("/runs/{run_id}/sign-off")
def sign_off(
    run_id: str, body: SignOffBody, request: Request,
    x_qc_role: str | None = Header(default=None),
) -> dict:
    role = _role(x_qc_role)
    _require_reviewer(role)
    if body.state not in {"signed_off", "returned", "in_review"}:
        raise HTTPException(status_code=422, detail="state must be signed_off, returned, or in_review")
    payload = request.app.state.repo.sign_off(run_id, body.state, body.reviewer, role)
    if payload is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return payload


@router.get("/runs/{run_id}/audit")
def audit_log(
    run_id: str, request: Request,
    x_qc_role: str | None = Header(default=None),
) -> list[dict]:
    _require_reviewer(_role(x_qc_role))
    return request.app.state.repo.audit_log(run_id)
