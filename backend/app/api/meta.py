from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/meta")
def meta(request: Request) -> dict:
    state = request.app.state
    return {
        "schema_version": state.adapter.schema_version,
        "ruleset_version": state.ruleset_version,
        "rule_count": len(state.rules),
    }
