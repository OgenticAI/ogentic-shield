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

# Deployment knobs (no code change / no redeploy of the image needed):
#   SHIELD_PROFILES  — comma-separated profile ids (default: finance,legal,therapy)
#   SHIELD_NER_MODEL — spaCy model for the NER layer. "en_core_web_lg" (accuracy,
#                      ~780 MB) or "en_core_web_sm" (~165 MB — fits a 512 MB box /
#                      serverless). Default sm here: the service is memory-bound,
#                      and the ~5x saving is what keeps it from OOM-crashing on a
#                      small plan. Set to lg on a ≥2 GB box for max NER recall.
_PROFILES = [p.strip() for p in os.environ.get("SHIELD_PROFILES", "").split(",") if p.strip()] \
    or DEFAULT_PROFILES
_NER_MODEL = os.environ.get("SHIELD_NER_MODEL") or "en_core_web_sm"

_shield: Any = None
_shield_lock = threading.Lock()


def _get_shield() -> Any:
    global _shield
    if _shield is None:
        with _shield_lock:
            if _shield is None:
                from ogentic_shield import Shield  # heavy import — deferred
                from ogentic_shield.config import ShieldConfig

                _shield = Shield(
                    profiles=_PROFILES,
                    config=ShieldConfig(profiles=_PROFILES, ner_model=_NER_MODEL),
                )
    return _shield


def _val(x: Any) -> Any:
    return x.value if isinstance(x, Enum) else x


app = FastAPI(title="ogentic-shield", version="0.6")


@app.on_event("startup")
def _warm_pipeline() -> None:
    # Warm the import + model in the background so the first real /analyze isn't
    # slow (the TS client times out at 10s), without delaying uvicorn bind.
    threading.Thread(target=_get_shield, daemon=True).start()


class AnalyzeRequest(BaseModel):
    text: str
    profiles: list[str] | None = None


@app.get("/")
def root() -> dict[str, Any]:
    # Unauthenticated service banner — identity + how to use it, no analysis, no secrets.
    return {
        "service": "ogentic-shield",
        "version": app.version,
        "status": "ok",
        "description": (
            "Shield redaction service — detects PII / sensitive entities "
            "(Presidio + spaCy, regex + NER + rules) for OgenticAI Zashboard's "
            "governed loop."
        ),
        "endpoints": {
            "GET /": "this service banner",
            "GET /health": "liveness probe → {ok: true}",
            "POST /analyze": (
                "body {text, profiles?}; optional 'Authorization: Bearer <SHIELD_API_KEY>'; "
                "returns {text_hash, entities[], score, sensitivity_level, "
                "routing_suggestion, ...}"
            ),
        },
        "default_profiles": DEFAULT_PROFILES,
        "auth": "required" if _API_KEY else "open",
        "source": "https://github.com/OgenticAI/ogentic-shield",
    }


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
