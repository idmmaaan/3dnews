#!/usr/bin/env python3
"""End-to-end smoke test — Scrape @CNN → Gemini translate → Post to Telegram.

Run directly:  python test_pipeline.py

This script does NOT use the database — it's a standalone test of the three
core services: X Scraper → LLM → Telegram.
"""

from __future__ import annotations

import asyncio
import logging
import sys

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_pipeline")


def banner(title: str) -> None:
    """Print a visible section banner."""
    sep = "=" * 60
    logger.info("")
    logger.info(sep)
    logger.info("  %s", title)
    logger.info(sep)


async def main() -> None:
    """Run one full end-to-end pipeline pass (single tweet)."""

    # ── STEP 1: Scrape tweets from X ──────────────────────────────────
    banner("STEP 1 — Scrape tweets from X (@CNN)")

    from app.services.x_scraper import fetch_recent_tweets

    tweets = await fetch_recent_tweets()

    if not tweets:
        logger.error("No tweets fetched — cannot continue. Check credentials.")
        sys.exit(1)

    logger.info("Fetched %d tweets total.", len(tweets))
    for i, t in enumerate(tweets, 1):
        logger.info(
            "  [%d] @%s | id=%s | img=%s\n       Text: %s",
            i, t.author_username, t.tweet_id,
            "YES" if t.image_url else "NO",
            t.text.replace("\n", " "),
        )

    # Pick the first tweet for the full pipeline test
    tweet = tweets[0]
    logger.info("Selected tweet %s from @%s for full pipeline test.", tweet.tweet_id, tweet.author_username)

    # ── STEP 2: Summarise via Gemini ──────────────────────────────────
    banner("STEP 2 — Gemini Generate English Summary")

    from app.services.llm import summarize_tweet

    summary = await summarize_tweet(
        text=tweet.text,
        author=tweet.author_username,
    )

    logger.info("LLM result:\n%s", summary)

    # ── STEP 3: Post to Telegram ──────────────────────────────────────
    banner("STEP 3 — Post to Telegram channel")

    from app.services.telegram import post_to_channel, close_bot

    msg_id = await post_to_channel(
        text=summary,
        image_url=tweet.image_url,
    )

    if msg_id:
        logger.info("✅ Posted to Telegram — message_id=%d", msg_id)
    else:
        logger.error("❌ Failed to post to Telegram.")

    await close_bot()

    # ── Summary ───────────────────────────────────────────────────────
    banner("DONE — End-to-End Test Complete")
    logger.info("Tweet ID:    %s", tweet.tweet_id)
    logger.info("Author:      @%s", tweet.author_username)
    logger.info("Image:       %s", tweet.image_url or "(none)")
    logger.info("TG msg ID:   %s", msg_id or "(failed)")


if __name__ == "__main__":
    asyncio.run(main())
