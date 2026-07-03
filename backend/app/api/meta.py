from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/meta")
def meta(request: Request) -> dict:
    state = request.app.state
    rules, ruleset_version = state.rules_repo.active_rules()
    return {
        "schema_version": state.adapter.schema_version,
        "ruleset_version": ruleset_version,
        "rule_count": len(state.rules_repo.list_rules("all")),
        "active_rule_count": sum(1 for r in rules if r.enabled),
        "profiles": [p["name"] for p in state.rules_repo.list_profiles()],
    }
