"""
ogentic-shield HTTP service — the `/analyze` endpoint the TS ShieldClient calls.

The PyPI package ships a library + CLI + MCP server but no REST server; this thin
FastAPI wrapper exposes `POST /analyze` in the exact contract
`packages/shield/src/client.ts` expects (snake_case), backed by the full
Presidio + spaCy pipeline (regex + NER + rules). Deploy as a container (see
deploy/README.md) and point the app's SHIELD_URL at it.

Both the `ogentic_shield` import AND the Presidio/spaCy pipeline build are done
lazily (first `/analyze`, warmed in a background thread at startup) so the module
loads instantly, uvicorn binds immediately, and `/health` passes the platform
healthcheck regardless of model-load time.
"""

from __future__ import annotations

import os
import threading
from enum import Enum
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

DEFAULT_PROFILES = ["shield-finance", "shield-legal", "shield-therapy"]
_API_KEY = os.environ.get("SHIELD_API_KEY") or ""

_shield: Any = None
_shield_lock = threading.Lock()


def _get_shield() -> Any:
    global _shield
    if _shield is None:
        with _shield_lock:
            if _shield is None:
                from ogentic_shield import Shield  # heavy import — deferred

                _shield = Shield(profiles=DEFAULT_PROFILES)
    return _shield


def _val(x: Any) -> Any:
    return x.value if isinstance(x, Enum) else x


app = FastAPI(title="ogentic-shield", version="0.4")


@app.on_event("startup")
def _warm_pipeline() -> None:
    # Warm the import + model in the background so the first real /analyze isn't
    # slow (the TS client times out at 10s), without delaying uvicorn bind.
    threading.Thread(target=_get_shield, daemon=True).start()


class AnalyzeRequest(BaseModel):
    text: str
    profiles: list[str] | None = None


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/analyze")
def analyze(req: AnalyzeRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if _API_KEY and authorization != f"Bearer {_API_KEY}":
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        result = _get_shield().analyze(req.text, profiles=req.profiles)
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
