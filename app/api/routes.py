"""FastAPI routes — health check and manual pipeline trigger."""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter

from app.services.pipeline import run_pipeline

router = APIRouter()


@router.get("/health", tags=["ops"])
async def health_check() -> dict[str, Any]:
    """Simple liveness / readiness probe."""
    return {
        "status": "ok",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.post("/trigger", tags=["ops"])
async def trigger_pipeline() -> dict[str, Any]:
    """Manually trigger a pipeline run (useful for debugging / testing)."""
    result = await run_pipeline()
    return {"pipeline": result}
