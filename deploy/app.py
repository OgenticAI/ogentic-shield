"""
ogentic-shield HTTP service — the `/analyze` endpoint the TS ShieldClient calls.

The PyPI package ships a library + CLI + MCP server but no REST server; this thin
FastAPI wrapper exposes `POST /analyze` in the exact contract
`packages/shield/src/client.ts` expects (snake_case), backed by the full
Presidio + spaCy pipeline (regex + NER + rules). Deploy as a container (see
deploy/README.md) and point the app's SHIELD_URL at it.

Run: uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from ogentic_shield import Shield  # published public API (>=0.4.0)

# Load the Presidio/spaCy pipeline ONCE at startup (heavy) and reuse per request;
# `analyze()` takes a per-call profile override so one instance serves all verticals.
DEFAULT_PROFILES = ["shield-finance", "shield-legal", "shield-therapy"]
_shield = Shield(profiles=DEFAULT_PROFILES)

_API_KEY = os.environ.get("SHIELD_API_KEY") or ""

app = FastAPI(title="ogentic-shield", version="0.4")


class AnalyzeRequest(BaseModel):
    text: str
    profiles: list[str] | None = None


def _val(x: Any) -> Any:
    return x.value if isinstance(x, Enum) else x


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/analyze")
def analyze(req: AnalyzeRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if _API_KEY and authorization != f"Bearer {_API_KEY}":
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        result = _shield.analyze(req.text, profiles=req.profiles)
    except Exception as exc:  # unknown profile id, etc. → 400, never leak internals
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "text_hash": result.text_hash,
        "entities": [
            {
                "text": e.text,
                "category": e.category,
                "category_group": _val(e.category_group),
                "confidence": e.confidence,
                "detection_layer": _val(e.detection_layer),
                "start": e.start,
                "end": e.end,
                "metadata": e.metadata or {},
            }
            for e in result.entities
        ],
        "score": result.score,
        "sensitivity_level": _val(result.sensitivity_level),
        "routing_suggestion": result.routing_suggestion,
        "entity_count": result.entity_count,
        "processing_time_ms": result.processing_time_ms,
        "layers_invoked": [_val(layer) for layer in result.layers_invoked],
        "profile_ids": result.profile_ids,
    }
