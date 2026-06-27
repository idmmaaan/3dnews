"""LLM service — summarise a tweet and translate to Russian via Gemini."""

from __future__ import annotations

import asyncio
import json
import logging

import google.generativeai as genai

from app.core.config import settings

logger = logging.getLogger(__name__)

_configured: bool = False


def _ensure_configured() -> None:
    """Configure the Gemini SDK if not already configured."""
    global _configured  # noqa: PLW0603
    if not _configured:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


SYSTEM_PROMPT = """\
You are an expert news curator for a Telegram channel.

Your task:
1. Read the original English tweet below.
2. Write a concise, factual summary of the core news or message in English.
3. Remove ANY links or URLs. Do not include them in your output.
4. Format the result for Telegram:
   • Start with a relevant emoji that matches the topic (🔥 war, 💰 economics, 🏛 politics, 🚨 crime, 🌍 migration, etc.).
   • Use bold (**text**) for the headline / most important fact.
   • Keep it extremely brief (1-3 sentences maximum).
   • Add the source handle in parentheses at the end, e.g. (@CNN).
5. Do NOT add hashtags.
"""

BATCH_TOPIC_FILTER_PROMPT = """\
You are a news topic classifier.

Determine if each tweet in the provided JSON list is about ANY of these topics:
- Politics (government, elections, legislation, diplomacy, sanctions, political parties)
- Economics (economy, finance, markets, trade, inflation, GDP, banking, business)
- War (military, armed conflicts, defense, weapons, NATO, troops, battles)
- Migrants / Immigration (refugees, asylum, immigration policy, border, deportation)
- Criminal (crime, arrests, investigations, fraud, corruption, court cases, sentencing)

The input will be a JSON array of tweets, e.g. [{"id": "1", "author": "@CNN", "text": "..."}].
You MUST output ONLY a JSON array of boolean values (true or false), perfectly matching the order of the input tweets.
Example output: [true, false, true, false]
Do not explain. Do not add anything else.
"""


async def summarize_tweet(text: str, author: str) -> str:
    """Send tweet text to Gemini LLM, return formatted English summary."""
    _ensure_configured()
    
    model = genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
        generation_config={"temperature": 0.4, "max_output_tokens": 4000}
    )

    user_message = f"Author: @{author}\n\nTweet:\n{text}"

    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            response = await model.generate_content_async(user_message)
            result = response.text or ""
            logger.info("LLM translation completed for @%s tweet. Finish reason: %s", author, response.candidates[0].finish_reason)
            return result.strip()

        except Exception as e:
            error_str = str(e).lower()
            if "rate_limit" in error_str or "429" in error_str or "quota" in error_str:
                if attempt < max_retries:
                    wait = 10 * (2 ** attempt)  # 10s, 20s, 40s
                    logger.warning(
                        "Gemini rate limit hit (attempt %d/%d), retrying in %ds…",
                        attempt + 1, max_retries, wait,
                    )
                    await asyncio.sleep(wait)
                    continue
            logger.exception("LLM call failed for @%s tweet.", author)
            raise

    raise RuntimeError("LLM call exhausted all retries.")


async def batch_classify_topics(tweets: list[dict]) -> list[bool]:
    """Check a list of tweets for topic relevance in one LLM call to save tokens.
    tweets is a list of dicts: [{"id": "...", "author": "...", "text": "..."}]
    """
    if not tweets:
        return []
        
    _ensure_configured()
    
    model = genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        system_instruction=BATCH_TOPIC_FILTER_PROMPT,
        generation_config={"temperature": 0.0, "response_mime_type": "application/json"}
    )
    user_message = json.dumps(tweets, ensure_ascii=False)

    try:
        response = await model.generate_content_async(user_message)
        result_text = (response.text or "").strip()
        
        # Handle cases where model outputs markdown backticks
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
            
        answers = json.loads(result_text.strip())
        
        if not isinstance(answers, list) or len(answers) != len(tweets):
            logger.error("Batch classification returned invalid array length. Defaulting to True.")
            return [True] * len(tweets)
            
        for i, ans in enumerate(answers):
            logger.info(
                "Batch topic filter for @%s tweet %s: %s",
                tweets[i]["author"], tweets[i]["id"], "RELEVANT" if ans else "SKIP"
            )
        return [bool(a) for a in answers]

    except Exception:
        logger.exception("Batch topic classification failed — including all by default.")
        return [True] * len(tweets)
