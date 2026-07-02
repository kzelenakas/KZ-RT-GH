from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError

router = APIRouter(prefix="/api/admin")


def _require_admin(x_qc_role: str | None) -> None:
    # Beta role model (role switcher header); IAP identity augments this at deploy.
    if (x_qc_role or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


class ToggleBody(BaseModel):
    enabled: bool


class ProfileBody(BaseModel):
    name: str
    description: str = ""
    disabled_rule_ids: list[str] = []


class ImportBody(BaseModel):
    ruleset: dict
    replace: bool = False


@router.get("/rules")
def list_rules(request: Request, status: str = "all", x_qc_role: str | None = Header(default=None)) -> list[dict]:
    _require_admin(x_qc_role)
    if status not in {"all", "enabled", "needs_encoding"}:
        raise HTTPException(status_code=422, detail="status must be all, enabled, or needs_encoding")
    return request.app.state.rules_repo.list_rules(status)


@router.get("/rules/{rule_id}")
def get_rule(rule_id: str, request: Request, x_qc_role: str | None = Header(default=None)) -> dict:
    _require_admin(x_qc_role)
    rule = request.app.state.rules_repo.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.put("/rules/{rule_id}")
def upsert_rule(rule_id: str, definition: dict, request: Request, x_qc_role: str | None = Header(default=None)) -> dict:
    _require_admin(x_qc_role)
    definition["rule_id"] = rule_id
    try:
        return request.app.state.rules_repo.upsert_rule(definition)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/rules/{rule_id}/toggle")
def toggle_rule(rule_id: str, body: ToggleBody, request: Request, x_qc_role: str | None = Header(default=None)) -> dict:
    _require_admin(x_qc_role)
    rule = request.app.state.rules_repo.set_enabled(rule_id, body.enabled)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.post("/rules/{rule_id}/archive")
def archive_rule(rule_id: str, request: Request, x_qc_role: str | None = Header(default=None)) -> dict:
    _require_admin(x_qc_role)
    if not request.app.state.rules_repo.archive_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"archived": rule_id}


@router.get("/export")
def export_ruleset(request: Request, x_qc_role: str | None = Header(default=None)) -> dict:
    _require_admin(x_qc_role)
    return request.app.state.rules_repo.export_ruleset()


@router.post("/import")
def import_ruleset(body: ImportBody, request: Request, x_qc_role: str | None = Header(default=None)) -> dict:
    _require_admin(x_qc_role)
    try:
        count = request.app.state.rules_repo.import_ruleset(body.ruleset, replace=body.replace)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"imported": count}


@router.get("/profiles")
def list_profiles(request: Request, x_qc_role: str | None = Header(default=None)) -> list[dict]:
    _require_admin(x_qc_role)
    return request.app.state.rules_repo.list_profiles()


@router.post("/profiles")
def upsert_profile(body: ProfileBody, request: Request, x_qc_role: str | None = Header(default=None)) -> dict:
    _require_admin(x_qc_role)
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Profile name required")
    return request.app.state.rules_repo.upsert_profile(body.name.strip(), body.description, body.disabled_rule_ids)
