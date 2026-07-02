from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.api import admin, exports, meta, reviews, runs
from app.persistence import RulesRepository, RunRepository, init_db
from app.schema_adapters import get_default_adapter


def create_app() -> FastAPI:
    app = FastAPI(title="UAD 3.6 QC", version="0.1.0")
    app.state.adapter = get_default_adapter()
    sessions = init_db(config.DB_URL)
    app.state.repo = RunRepository(sessions)
    app.state.rules_repo = RulesRepository(sessions)
    # First boot: seed the rules DB from the external ruleset file (H-1 import).
    app.state.rules_repo.seed_from_file(config.RULES_PATH)

    # Dev convenience: allow the Vite dev server origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(runs.router)
    app.include_router(reviews.router)
    app.include_router(exports.router)
    app.include_router(admin.router)
    app.include_router(meta.router)

    if config.FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
    return app


app = create_app()
