"""Pluggable AI backends for rules with logic type "ai".

GLBA guardrail: the Gemini API (developer key) MUST only see sample/test data —
free-tier keys allow Google to train on inputs. Real borrower data goes through
Vertex AI on the company-controlled GCP project. create_app() enforces this via
QC_DATA_CLASS (see app.main).

Rule logic contract:
    {"type": "ai", "prompt": "<instruction>", "fields": ["<field key>", ...]}

The backend receives the prompt plus the named field values and must decide
whether the rule fires. Backends return AIResult(triggered, rationale).
"""

from __future__ import annotations

import json
import re
from typing import Protocol

import httpx
from pydantic import BaseModel


class AIResult(BaseModel):
    triggered: bool
    rationale: str = ""


class AIBackend(Protocol):
    name: str

    def evaluate(self, prompt: str, context: dict[str, str | None]) -> AIResult: ...


class StubBackend:
    """Offline backend: never fires. Keeps the engine testable and the app
    runnable with zero AI cost/config."""

    name = "stub"

    def evaluate(self, prompt: str, context: dict[str, str | None]) -> AIResult:
        return AIResult(triggered=False, rationale="Stub AI backend (no live model configured).")


_INSTRUCTION = (
    "You are a QC rule evaluator for residential appraisal reports. "
    "Apply the rule below to the provided field values. "
    'Respond with ONLY a JSON object: {"triggered": true|false, "explanation": "<one sentence>"} '
    "where triggered=true means the rule FIRES (a problem was found).\n\n"
    "Rule: {prompt}\n\nField values:\n{context}"
)


def _parse_ai_json(text: str) -> AIResult:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"AI response contained no JSON object: {text[:200]!r}")
    data = json.loads(match.group(0))
    return AIResult(triggered=bool(data.get("triggered")), rationale=str(data.get("explanation", "")))


class GeminiAPIBackend:
    """Google AI Studio (developer API key). SAMPLE DATA ONLY — see module note."""

    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._model = model

    def evaluate(self, prompt: str, context: dict[str, str | None]) -> AIResult:
        body = {
            "contents": [{
                "parts": [{
                    "text": _INSTRUCTION.format(
                        prompt=prompt,
                        context=json.dumps(context, indent=2),
                    ),
                }],
            }],
            "generationConfig": {"temperature": 0},
        }
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent",
            params={"key": self._api_key},
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_ai_json(text)


class VertexAIBackend:
    """Vertex AI on the company GCP project (real-data path). Uses Application
    Default Credentials; configure QC_VERTEX_PROJECT / QC_VERTEX_LOCATION."""

    name = "vertex"

    def __init__(self, project: str, location: str = "us-central1", model: str = "gemini-2.0-flash"):
        self._project = project
        self._location = location
        self._model = model

    def evaluate(self, prompt: str, context: dict[str, str | None]) -> AIResult:
        try:
            import google.auth
            import google.auth.transport.requests
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Vertex backend needs google-auth: pip install google-auth"
            ) from exc
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(google.auth.transport.requests.Request())
        url = (
            f"https://{self._location}-aiplatform.googleapis.com/v1/projects/{self._project}"
            f"/locations/{self._location}/publishers/google/models/{self._model}:generateContent"
        )
        body = {
            "contents": [{
                "role": "user",
                "parts": [{
                    "text": _INSTRUCTION.format(prompt=prompt, context=json.dumps(context, indent=2)),
                }],
            }],
            "generationConfig": {"temperature": 0},
        }
        response = httpx.post(
            url, json=body, timeout=30,
            headers={"Authorization": f"Bearer {credentials.token}"},
        )
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_ai_json(text)


def build_backend(kind: str, *, gemini_api_key: str = "", vertex_project: str = "",
                  vertex_location: str = "us-central1", model: str = "gemini-2.0-flash") -> AIBackend:
    kind = (kind or "stub").lower()
    if kind == "stub":
        return StubBackend()
    if kind == "gemini":
        if not gemini_api_key:
            raise ValueError("QC_GEMINI_API_KEY is required for the gemini backend")
        return GeminiAPIBackend(gemini_api_key, model)
    if kind == "vertex":
        if not vertex_project:
            raise ValueError("QC_VERTEX_PROJECT is required for the vertex backend")
        return VertexAIBackend(vertex_project, vertex_location, model)
    raise ValueError(f"Unknown AI backend: {kind!r} (expected stub, gemini, or vertex)")
