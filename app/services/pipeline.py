"""Pipeline orchestrator — glues X Scraper → LLM → Telegram together."""

from __future__ import annotations

import json
import logging
import os
import re

from app.core.config import settings
from app.services.llm import batch_classify_topics, summarize_tweet
from app.services.telegram import post_to_channel
from app.services.x_scraper import FetchedTweet, fetch_recent_tweets

logger = logging.getLogger(__name__)

# ── File-based dedup (used when DB is unavailable) ────────────────────
_DEDUP_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "processed_ids.json"
)


def _load_processed_ids() -> set[str]:
    """Load previously processed tweet IDs from JSON file."""
    path = os.path.normpath(_DEDUP_FILE)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return set(json.load(f))
        except Exception:
            logger.warning("Could not read %s — starting fresh.", path)
    return set()


def _save_processed_ids(ids: set[str]) -> None:
    """Persist processed tweet IDs to JSON file."""
    path = os.path.normpath(_DEDUP_FILE)
    try:
        with open(path, "w") as f:
            json.dump(sorted(ids), f)
    except Exception:
        logger.exception("Failed to save processed IDs to %s", path)


def _try_import_db():
    """Try to import DB components; return None if unavailable."""
    try:
        from sqlalchemy import select
        from app.core.database import async_session
        from app.models.news import ProcessedItem
        return select, async_session, ProcessedItem
    except Exception:
        return None


async def run_pipeline() -> dict:
    """Execute one full pipeline cycle.

    Steps
    -----
    1. Scrape recent tweets from configured X accounts via Playwright.
    2. Deduplicate (DB if available, otherwise JSON file).
    3. Filter by topic (politics, economics, war, migrants, criminal).
    4. For each relevant tweet:
       a. Summarise + translate via LLM.
       b. Post to Telegram.
       c. Mark as processed.
    5. Return a summary dict of the run.
    """
    logger.info("🚀 Pipeline run started.")

    # ── 1. Fetch ──────────────────────────────────────────────────────
    try:
        tweets: list[FetchedTweet] = await fetch_recent_tweets()
    except Exception:
        logger.exception("Failed to fetch tweets — aborting pipeline run.")
        return {"status": "error", "stage": "fetch", "processed": 0}

    if not tweets:
        logger.info("No tweets returned — nothing to process.")
        return {"status": "ok", "processed": 0, "skipped": 0}

    # ── 2. Deduplicate ────────────────────────────────────────────────
    tweet_ids = [t.tweet_id for t in tweets]
    db = _try_import_db()

    if db is not None:
        select, async_session, ProcessedItem = db
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(ProcessedItem.item_id).where(
                        ProcessedItem.item_id.in_(tweet_ids)
                    )
                )
                already_processed: set[str] = set(result.scalars().all())
            use_db = True
        except Exception:
            logger.warning("DB unavailable — falling back to file-based dedup.")
            already_processed = _load_processed_ids()
            use_db = False
    else:
        already_processed = _load_processed_ids()
        use_db = False

    new_tweets = [t for t in tweets if t.tweet_id not in already_processed]
    skipped = len(tweets) - len(new_tweets)
    logger.info(
        "Deduplication: %d new, %d already processed.", len(new_tweets), skipped
    )

    if not new_tweets:
        return {"status": "ok", "processed": 0, "skipped": skipped}

    # ── 3. Topic filtering ────────────────────────────────────────────
    relevant_tweets: list[FetchedTweet] = []
    if new_tweets:
        # Prepare batch input
        batch_input = [
            {"id": t.tweet_id, "author": t.author_username, "text": t.text}
            for t in new_tweets
        ]
        
        # Call batch API once for all new tweets
        results = await batch_classify_topics(batch_input)
        
        for tweet, is_relevant in zip(new_tweets, results):
            if is_relevant:
                relevant_tweets.append(tweet)
            else:
                logger.info(
                    "⏭️  Skipping tweet %s from @%s — topic not relevant.",
                    tweet.tweet_id, tweet.author_username,
                )

    filtered_out = len(new_tweets) - len(relevant_tweets)
    logger.info(
        "Topic filter: %d relevant, %d filtered out.", len(relevant_tweets), filtered_out
    )

    if not relevant_tweets:
        logger.info("No tweets matched allowed topics — nothing to post.")
        # Still mark all as processed so we don't re-check them
        if not use_db:
            all_ids = already_processed | {t.tweet_id for t in new_tweets}
            _save_processed_ids(all_ids)
        return {"status": "ok", "processed": 0, "skipped": skipped, "filtered": filtered_out}

    # Limit to 5 per run to respect rate limits
    if len(relevant_tweets) > 5:
        logger.info("Limiting to 5 tweets to respect rate limits.")
        relevant_tweets = relevant_tweets[:5]

    # ── 4. Process each relevant tweet ────────────────────────────────
    processed_count = 0
    errors = 0
    newly_processed_ids: set[str] = set()

    for tweet in relevant_tweets:
        try:
            # 4a. Clean and Summarise
            clean_text = re.sub(r'https?://\S+', '', tweet.text).strip()
            
            if settings.ENABLE_LLM_SUMMARIZATION:
                summary = await summarize_tweet(
                    text=clean_text,
                    author=tweet.author_username,
                )
            else:
                summary = f"{clean_text}\n\n(@{tweet.author_username})"

            # 4b. Post to Telegram
            tg_msg_id = await post_to_channel(
                text=summary,
                image_url=tweet.image_url,
            )

            # 4c. Persist
            if use_db:
                try:
                    select, async_session, ProcessedItem = db
                    async with async_session() as session:
                        record = ProcessedItem(
                            item_id=tweet.tweet_id,
                            author_source=f"@{tweet.author_username}",
                            original_title=tweet.text[:500],
                            translated_text=summary,
                            image_url=tweet.image_url,
                            telegram_message_id=tg_msg_id,
                        )
                        session.add(record)
                        await session.commit()
                except Exception:
                    logger.warning("DB persist failed — using file dedup as fallback.")

            newly_processed_ids.add(tweet.tweet_id)
            processed_count += 1
            logger.info(
                "✅ Processed tweet %s from @%s.",
                tweet.tweet_id,
                tweet.author_username,
            )

        except Exception:
            errors += 1
            logger.exception(
                "❌ Failed to process tweet %s from @%s.",
                tweet.tweet_id,
                tweet.author_username,
            )

    # Also mark all new tweets (including filtered ones) as processed
    if not use_db:
        all_ids = already_processed | {t.tweet_id for t in new_tweets} | newly_processed_ids
        _save_processed_ids(all_ids)

    summary = {
        "status": "ok" if errors == 0 else "partial",
        "processed": processed_count,
        "errors": errors,
        "skipped": skipped,
        "filtered": filtered_out,
    }
    logger.info("Pipeline run finished: %s", summary)
    return summary
