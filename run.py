#!/usr/bin/env python3
"""Standalone background runner — runs the pipeline in a loop without FastAPI or PostgreSQL.

Usage:
    python run.py              # run once immediately, then every POLL_INTERVAL_MINUTES
    python run.py --once       # run once and exit

This is the recommended way to run locally without Docker.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run")

_shutdown = False


def _handle_signal(sig, frame):
    global _shutdown
    logger.info("Received signal %s — shutting down after current run…", sig)
    _shutdown = True


async def main() -> None:
    from app.core.config import settings
    from app.services.pipeline import run_pipeline
    from app.services.telegram import close_bot

    once = "--once" in sys.argv
    interval = settings.POLL_INTERVAL_MINUTES * 60

    logger.info("━" * 60)
    logger.info("  News Pipeline — Standalone Runner")
    logger.info("  Interval: %d minutes", settings.POLL_INTERVAL_MINUTES)
    logger.info("  Mode: %s", "single run" if once else "continuous loop")
    logger.info("  Topics: politics, economics, war, migrants, criminal")
    logger.info("━" * 60)

    try:
        while True:
            try:
                result = await run_pipeline()
                logger.info("Run result: %s", result)
            except Exception:
                logger.exception("Pipeline run failed.")

            if once or _shutdown:
                break

            logger.info("Sleeping %d minutes until next run…", settings.POLL_INTERVAL_MINUTES)
            # Sleep in small chunks so we can respond to signals
            for _ in range(interval):
                if _shutdown:
                    break
                await asyncio.sleep(1)
    finally:
        await close_bot()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    asyncio.run(main())
