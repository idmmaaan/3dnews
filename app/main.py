"""FastAPI application entry point with APScheduler integration."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.services.pipeline import run_pipeline
from app.services.telegram import close_bot

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Scheduler ─────────────────────────────────────────────────────────
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle events."""
    # ── Startup ───────────────────────────────────────────────────────
    logger.info(
        "Starting scheduler — pipeline will run every %d minutes.",
        settings.POLL_INTERVAL_MINUTES,
    )
    scheduler.add_job(
        run_pipeline,
        trigger="interval",
        minutes=settings.POLL_INTERVAL_MINUTES,
        id="news_pipeline",
        name="News curation pipeline",
        replace_existing=True,
    )
    scheduler.start()

    yield

    # ── Shutdown ──────────────────────────────────────────────────────
    logger.info("Shutting down scheduler…")
    scheduler.shutdown(wait=False)
    await close_bot()
    logger.info("Shutdown complete.")


# ── App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="News Curation Pipeline",
    description="Automated Twitter → LLM → Telegram news pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)
