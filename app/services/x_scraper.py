"""X / Twitter scraper — Playwright with cookie injection + GraphQL interception."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from playwright.async_api import async_playwright, Page, BrowserContext

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FetchedTweet:
    """Lightweight container for a scraped tweet."""

    tweet_id: str
    author_username: str
    text: str
    image_url: str | None
    created_at: str


def _extract_tweets_from_data(data: dict, handle: str) -> list[FetchedTweet]:
    """Walk the deeply-nested GraphQL response JSON and pull out tweets."""
    results: list[FetchedTweet] = []

    try:
        # Navigate the nested timeline structure
        instructions = (
            data
            .get("data", {})
            .get("user", {})
            .get("result", {})
            .get("timeline_v2", data.get("data", {}).get("user", {}).get("result", {}).get("timeline", {}))
            .get("timeline", {})
            .get("instructions", [])
        )

        entries: list[dict] = []
        for instr in instructions:
            if instr.get("type") == "TimelineAddEntries":
                entries = instr.get("entries", [])
                break

        for entry in entries:
            try:
                content = entry.get("content", {})
                if content.get("entryType") != "TimelineTimelineItem":
                    continue

                item_content = content.get("itemContent", {})
                if item_content.get("itemType") != "TimelineTweet":
                    continue

                tweet_results = item_content.get("tweet_results", {}).get("result", {})

                # Handle promoted tweets or tombstones
                typename = tweet_results.get("__typename", "")
                if typename == "TweetWithVisibilityResults":
                    tweet_results = tweet_results.get("tweet", {})
                elif typename != "Tweet":
                    continue

                # Skip retweets
                legacy = tweet_results.get("legacy", {})
                if legacy.get("retweeted_status_result"):
                    continue

                tweet_id = legacy.get("id_str", tweet_results.get("rest_id", ""))
                text = legacy.get("full_text", "")
                
                # Handle long tweets (Twitter "Notes" feature) where full_text is truncated
                note_text = tweet_results.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {}).get("text")
                if note_text:
                    text = note_text
                    
                created_at = legacy.get("created_at", "")

                # Get author info
                core = tweet_results.get("core", {}).get("user_results", {}).get("result", {})
                author = core.get("legacy", {}).get("screen_name", handle)

                # Extract first photo
                image_url: str | None = None
                media_list = legacy.get("extended_entities", {}).get("media", [])
                if not media_list:
                    media_list = legacy.get("entities", {}).get("media", [])
                for media in media_list:
                    if media.get("type") == "photo":
                        image_url = media.get("media_url_https", media.get("media_url"))
                        break

                if tweet_id and text:
                    results.append(FetchedTweet(
                        tweet_id=tweet_id,
                        author_username=author,
                        text=text,
                        image_url=image_url,
                        created_at=created_at,
                    ))

            except Exception:
                continue  # skip malformed entries

    except Exception:
        logger.exception("Failed to parse GraphQL tweet data.")

    return results


async def _scrape_profile(context: BrowserContext, handle: str) -> list[FetchedTweet]:
    """Navigate to an X profile and intercept the GraphQL tweets response."""
    tweets: list[FetchedTweet] = []
    captured_data: list[dict] = []

    page: Page = await context.new_page()

    async def handle_response(response):
        """Intercept GraphQL responses containing tweet data."""
        url = response.url
        if "UserTweets" in url or "UserByScreenName" in url:
            try:
                if response.status == 200:
                    body = await response.json()
                    if "UserTweets" in url:
                        captured_data.append(body)
                        logger.info("Captured UserTweets GraphQL response for @%s", handle)
            except Exception:
                pass

    page.on("response", handle_response)

    try:
        logger.info("Navigating to https://x.com/%s …", handle)

        # Use domcontentloaded — X never reaches networkidle due to
        # constant background activity (analytics, streaming, etc.)
        try:
            await page.goto(
                f"https://x.com/{handle}",
                wait_until="domcontentloaded",
                timeout=20000,
            )
        except Exception as nav_err:
            # Even if nav times out, we may already have captured data
            logger.warning("Navigation issue for @%s (may still have data): %s", handle, nav_err)

        # Wait for GraphQL responses to arrive
        for _ in range(10):
            if captured_data:
                break
            await asyncio.sleep(1)

        # If still no data, try scrolling to trigger lazy load
        if not captured_data:
            logger.info("No initial data, scrolling to trigger load…")
            try:
                await page.evaluate("window.scrollBy(0, 1000)")
                await asyncio.sleep(3)
            except Exception:
                pass

        for data in captured_data:
            tweets.extend(_extract_tweets_from_data(data, handle))

        logger.info("Extracted %d tweets from @%s", len(tweets), handle)

    except Exception:
        logger.exception("Error scraping @%s", handle)
    finally:
        await page.close()

    return tweets


async def fetch_recent_tweets() -> list[FetchedTweet]:
    """Fetch recent tweets from configured X accounts using Playwright.

    Injects auth_token + ct0 cookies, navigates to each profile,
    and intercepts GraphQL API responses.
    """
    accounts = settings.x_account_list
    if not accounts:
        logger.warning("No X accounts configured — skipping fetch.")
        return []

    if not settings.X_AUTH_TOKEN or not settings.X_CT0:
        logger.error(
            "X_AUTH_TOKEN and X_CT0 must be set in .env. "
            "See README for cookie extraction instructions."
        )
        return []

    all_tweets: list[FetchedTweet] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # Create browser context with cookies injected
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        # Inject the two essential cookies
        await context.add_cookies([
            {
                "name": "auth_token",
                "value": settings.X_AUTH_TOKEN,
                "domain": ".x.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            },
            {
                "name": "ct0",
                "value": settings.X_CT0,
                "domain": ".x.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            },
        ])

        for handle in accounts:
            try:
                tweets = await _scrape_profile(context, handle)
                # Limit per account
                all_tweets.extend(tweets[:settings.X_TWEETS_PER_ACCOUNT])
            except Exception:
                logger.exception("Failed to scrape @%s", handle)

        await context.close()
        await browser.close()

    logger.info("Total fetched: %d tweets from %d accounts.", len(all_tweets), len(accounts))
    return all_tweets
